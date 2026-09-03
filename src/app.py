import hashlib
import ipaddress
import json
import os
import re
import socket
import sqlite3
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request


app = Flask(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CUSTOM_GLOSSARY_PATH = DATA_DIR / "custom_glossary.json"
GLOSSARY_SOURCES = (
    ("Workplace", DATA_DIR / "workplace_glossary.json", 1),
    ("CRM", DATA_DIR / "crm_glossary.json", 2),
    ("Custom", CUSTOM_GLOSSARY_PATH, 3),
)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3")
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "15m")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "45"))
MAX_TRANSLATE_TEXT_LENGTH = 6000
TRANSLATE_CACHE_LIMIT = 64
TRANSLATE_EXPLAIN_CACHE = {}
SAVED_TERMS_DB_PATH = DATA_DIR / "saved_terms.db"
SAVED_TERM_SOURCES = {"Workplace", "CRM", "Custom", "AI"}
MAX_SAVED_TERM_LENGTH = 160
MAX_SAVED_TEXT_LENGTH = 2000
MAX_SAVED_TERM_STATUS_ITEMS = 12
MAX_LOOKUP_QUERY_LENGTH = 160
STATIC_ASSET_VERSION = "saved-term-status-1"

REQUIRED_GLOSSARY_TEXT_FIELDS = ("term", "english", "category", "explanation", "business_context")

AI_REQUIRED_FIELDS = {
    "natural_english_translation",
    "plain_english_meaning",
    "business_crm_context",
    "important_vocabulary",
    "developer_interpretation",
}
AI_OPTIONAL_TRANSLATE_FIELDS = {"line_translations"}
AI_VOCABULARY_FIELDS = {"french", "english", "explanation"}
AI_LOOKUP_FIELDS = {"english", "explanation", "business_context"}
LINE_TRANSLATION_FIELDS = {"french", "english"}
DEVELOPER_MODE_FIELDS = {
    "translation",
    "explicit_requirements",
    "implementation_notes",
    "important_vocabulary",
    "ambiguities",
}
MAX_DEVELOPER_LIST_ITEMS = 12


class GlossaryValidationError(ValueError):
    """Raised when a glossary file does not match the supported public schema."""


def normalize_text(value):
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    text = text.replace("’", "'")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", text)


def validate_glossary_entry(raw_entry, source, index):
    if not isinstance(raw_entry, dict):
        raise GlossaryValidationError(f"{source} glossary entry {index} must be an object.")

    entry = dict(raw_entry)
    # Support the v0 shape while canonicalizing it to the documented schema.
    if "literal_translation" not in entry and "literal" in entry:
        entry["literal_translation"] = entry["literal"]
    if "examples" not in entry and "example_fr" in entry and "example_en" in entry:
        entry["examples"] = [{"french": entry["example_fr"], "english": entry["example_en"]}]

    for field in REQUIRED_GLOSSARY_TEXT_FIELDS:
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            raise GlossaryValidationError(f"{source} glossary entry {index} has an invalid {field} field.")
    if not isinstance(entry.get("literal_translation", ""), str):
        raise GlossaryValidationError(f"{source} glossary entry {index} has an invalid literal_translation field.")
    if not isinstance(entry.get("related_terms"), list) or any(
        not isinstance(term, str) or not term.strip() for term in entry["related_terms"]
    ):
        raise GlossaryValidationError(f"{source} glossary entry {index} has invalid related_terms.")
    if not isinstance(entry.get("examples"), list) or not entry["examples"]:
        raise GlossaryValidationError(f"{source} glossary entry {index} must include at least one example.")

    examples = []
    for example in entry["examples"]:
        if not isinstance(example, dict) or set(example) != {"french", "english"}:
            raise GlossaryValidationError(f"{source} glossary entry {index} has an invalid example.")
        if any(not isinstance(example[field], str) or not example[field].strip() for field in ("french", "english")):
            raise GlossaryValidationError(f"{source} glossary entry {index} has an invalid example.")
        examples.append({field: example[field].strip() for field in ("french", "english")})

    return {
        "term": entry["term"].strip(),
        "english": entry["english"].strip(),
        "literal_translation": entry.get("literal_translation", "").strip(),
        "category": entry["category"].strip(),
        "explanation": entry["explanation"].strip(),
        "business_context": entry["business_context"].strip(),
        "examples": examples,
        "related_terms": [term.strip() for term in entry["related_terms"]],
    }


def normalize_entry(raw_entry, source, precedence, index):
    entry = validate_glossary_entry(raw_entry, source, index)
    entry["source"] = source
    entry["domain"] = source
    entry["precedence"] = precedence
    entry["search_terms"] = build_search_terms(entry)
    return entry


def build_search_terms(entry):
    candidates = [
        entry["term"],
        entry["english"],
        entry["literal_translation"],
        *entry["related_terms"],
    ]
    return sorted({normalize_text(candidate) for candidate in candidates if normalize_text(candidate)})


def load_glossary_file(path, source, precedence):
    try:
        with path.open(encoding="utf-8") as glossary_file:
            raw_entries = json.load(glossary_file)
    except (OSError, json.JSONDecodeError) as exc:
        if source == "Custom":
            raise GlossaryValidationError("Custom glossary is invalid. Check its JSON structure and schema.") from exc
        raise GlossaryValidationError(f"{source} glossary could not be loaded: {exc}") from exc

    if not isinstance(raw_entries, list):
        message = "Custom glossary must contain a JSON array." if source == "Custom" else f"{source} glossary must contain a JSON array."
        raise GlossaryValidationError(message)

    entries = [normalize_entry(raw_entry, source, precedence, index) for index, raw_entry in enumerate(raw_entries, start=1)]
    normalized_terms = [normalize_text(entry["term"]) for entry in entries]
    if len(normalized_terms) != len(set(normalized_terms)):
        message = "Custom glossary has duplicate normalized terms." if source == "Custom" else f"{source} glossary has duplicate normalized terms."
        raise GlossaryValidationError(message)
    return entries


def load_glossary(custom_path=CUSTOM_GLOSSARY_PATH):
    entries = []
    for source, path, precedence in GLOSSARY_SOURCES:
        if source == "Custom":
            path = custom_path
            if not path or not path.exists():
                continue
        entries.extend(load_glossary_file(path, source, precedence))

    return sorted(entries, key=lambda entry: (-entry["precedence"], normalize_text(entry["term"])))


def lookup_term(query, entries=None):
    normalized_query = normalize_text(query)
    if not normalized_query:
        return None

    glossary_entries = entries if entries is not None else DEFAULT_GLOSSARY

    ranked_entries = sorted(glossary_entries, key=lambda entry: (-entry["precedence"], normalize_text(entry["term"])))
    for entry in ranked_entries:
        if normalized_query == normalize_text(entry["term"]):
            return entry

    for entry in ranked_entries:
        if normalized_query in entry["search_terms"]:
            return entry

    for entry in ranked_entries:
        if any(normalized_query in search_term for search_term in entry["search_terms"]):
            return entry

    return None


DEFAULT_GLOSSARY = load_glossary()


def get_saved_terms_db_path():
    return Path(app.config.get("SAVED_TERMS_DB_PATH", SAVED_TERMS_DB_PATH))


def init_saved_terms_db(db_path=None):
    path = Path(db_path) if db_path else get_saved_terms_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_terms (
                id INTEGER PRIMARY KEY,
                normalized_term TEXT NOT NULL UNIQUE,
                french TEXT NOT NULL,
                english TEXT NOT NULL,
                literal_translation TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                explanation TEXT NOT NULL,
                business_context TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL,
                saved_at TEXT NOT NULL
            )
            """
        )


def connect_saved_terms_db():
    db_path = get_saved_terms_db_path()
    init_saved_terms_db(db_path)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def validate_saved_text(value, required=True, limit=MAX_SAVED_TEXT_LENGTH):
    if not isinstance(value, str):
        return None
    clean_value = value.strip()
    if (required and not clean_value) or len(clean_value) > limit:
        return None
    return clean_value


def build_saved_term_from_glossary(term):
    clean_term = validate_saved_text(term, limit=MAX_SAVED_TERM_LENGTH)
    if clean_term is None:
        return None
    entry = lookup_term(clean_term)
    if entry is None:
        return None
    return {
        "normalized_term": normalize_text(entry["term"]),
        "french": entry["term"],
        "english": entry["english"],
        "literal_translation": entry["literal_translation"],
        "category": entry["category"],
        "explanation": entry["explanation"],
        "business_context": entry["business_context"],
        "source": entry["source"],
    }


def build_saved_term_from_ai(payload):
    french = validate_saved_text(payload.get("french"), limit=MAX_SAVED_TERM_LENGTH)
    english = validate_saved_text(payload.get("english"))
    explanation = validate_saved_text(payload.get("explanation"))
    if not all((french, english, explanation)):
        return None
    return {
        "normalized_term": normalize_text(french),
        "french": french,
        "english": english,
        "literal_translation": "",
        "category": "",
        "explanation": explanation,
        "business_context": "",
        "source": "AI",
    }


def save_term(saved_term):
    saved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    values = {**saved_term, "saved_at": saved_at}
    try:
        with connect_saved_terms_db() as connection:
            cursor = connection.execute(
                """
                INSERT INTO saved_terms (
                    normalized_term, french, english, literal_translation, category,
                    explanation, business_context, source, saved_at
                ) VALUES (
                    :normalized_term, :french, :english, :literal_translation, :category,
                    :explanation, :business_context, :source, :saved_at
                )
                """,
                values,
            )
            saved_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        return None, False
    return saved_id, True


def list_saved_terms(query="", source=""):
    conditions = []
    parameters = []
    if query:
        conditions.append("(french LIKE ? COLLATE NOCASE OR english LIKE ? COLLATE NOCASE)")
        search_query = f"%{query}%"
        parameters.extend((search_query, search_query))
    if source:
        conditions.append("source = ?")
        parameters.append(source)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with connect_saved_terms_db() as connection:
        rows = connection.execute(
            f"SELECT * FROM saved_terms {where_clause} ORDER BY saved_at DESC, id DESC",
            parameters,
        ).fetchall()
        total = connection.execute("SELECT COUNT(*) FROM saved_terms").fetchone()[0]
    return [dict(row) for row in rows], total


def delete_saved_term(term_id):
    with connect_saved_terms_db() as connection:
        cursor = connection.execute("DELETE FROM saved_terms WHERE id = ?", (term_id,))
    return cursor.rowcount > 0


def get_saved_term_statuses(terms):
    normalized_terms = [normalize_text(term) for term in terms]
    placeholders = ", ".join("?" for _ in set(normalized_terms))
    with connect_saved_terms_db() as connection:
        rows = connection.execute(
            f"SELECT normalized_term FROM saved_terms WHERE normalized_term IN ({placeholders})",
            tuple(set(normalized_terms)),
        ).fetchall()
    saved_terms = {row["normalized_term"] for row in rows}
    return [term in saved_terms for term in normalized_terms]


def validate_translate_explain_result(result, source_text):
    if (
        not isinstance(result, dict)
        or not AI_REQUIRED_FIELDS <= set(result)
        or not set(result) <= AI_REQUIRED_FIELDS | AI_OPTIONAL_TRANSLATE_FIELDS
    ):
        return None

    natural_translation = normalize_natural_translation(result["natural_english_translation"], source_text)
    if natural_translation is None:
        return None
    if not isinstance(result["plain_english_meaning"], str) or not result["plain_english_meaning"].strip():
        return None

    for field in ("business_crm_context", "developer_interpretation"):
        if result[field] is not None and (not isinstance(result[field], str) or not result[field].strip()):
            return None

    clean_vocabulary = validate_important_vocabulary(result["important_vocabulary"], source_text=source_text)
    if clean_vocabulary is None:
        return None
    raw_line_translations = result.get("line_translations")
    line_translations = validate_line_translations(raw_line_translations, source_text)
    if raw_line_translations is None and not line_translations:
        line_translations = build_line_translations_from_translation(
            source_text, natural_translation
        )

    return {
        "natural_english_translation": natural_translation,
        "line_translations": line_translations,
        "plain_english_meaning": result["plain_english_meaning"].strip(),
        "business_crm_context": result["business_crm_context"].strip() if result["business_crm_context"] else None,
        "important_vocabulary": clean_vocabulary,
        "developer_interpretation": result["developer_interpretation"].strip() if result["developer_interpretation"] else None,
    }


def validate_string_list(value, limit):
    if isinstance(value, str):
        return [value.strip()] if value.strip() else None
    if not isinstance(value, list) or len(value) > limit:
        return None
    if any(not isinstance(item, str) or not item.strip() for item in value):
        return None
    return [item.strip() for item in value]


def vocabulary_term_appears_in_source(term, source_text):
    normalized_source = normalize_text(source_text)
    for candidate in re.split(r"\s*/\s*", normalize_text(term)):
        if candidate and re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", normalized_source):
            return True
    return False


def get_short_list_source_lines(source_text):
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    if not 2 <= len(lines) <= 12 or any(len(line) > 80 or len(line.split()) > 8 for line in lines):
        return []
    if any(re.search(r"[.!?](?:[\"')\]]*)$", line) for line in lines):
        return []
    return lines


def normalize_natural_translation(value, source_text):
    if isinstance(value, str) and value.strip():
        return value.strip()
    source_lines = get_short_list_source_lines(source_text)
    if (
        source_lines
        and isinstance(value, list)
        and len(value) == len(source_lines)
        and all(isinstance(line, str) and line.strip() for line in value)
    ):
        return "\n".join(line.strip() for line in value)
    return None


def validate_line_translations(line_translations, source_text):
    source_lines = get_short_list_source_lines(source_text)
    if not source_lines or not isinstance(line_translations, list) or len(line_translations) != len(source_lines):
        return []

    clean_lines = []
    for source_line, translation in zip(source_lines, line_translations):
        if not isinstance(translation, dict) or set(translation) != LINE_TRANSLATION_FIELDS:
            return []
        if any(not isinstance(translation[field], str) or not translation[field].strip() for field in LINE_TRANSLATION_FIELDS):
            return []
        if normalize_text(translation["french"]) != normalize_text(source_line):
            return []
        clean_lines.append({field: translation[field].strip() for field in LINE_TRANSLATION_FIELDS})
    return clean_lines


def build_line_translations_from_translation(source_text, natural_translation):
    source_lines = get_short_list_source_lines(source_text)
    english_lines = [line.strip() for line in natural_translation.splitlines() if line.strip()]
    if not source_lines or len(english_lines) != len(source_lines):
        return []
    return [
        {"french": french, "english": english}
        for french, english in zip(source_lines, english_lines)
    ]


def validate_important_vocabulary(vocabulary, source_text=None):
    if not isinstance(vocabulary, list) or len(vocabulary) > MAX_DEVELOPER_LIST_ITEMS:
        return None
    clean_vocabulary = []
    for item in vocabulary:
        if not isinstance(item, dict) or set(item) != AI_VOCABULARY_FIELDS:
            return None
        if any(not isinstance(item[field], str) or not item[field].strip() for field in AI_VOCABULARY_FIELDS):
            return None
        clean_item = {field: item[field].strip() for field in AI_VOCABULARY_FIELDS}
        if source_text is not None and not vocabulary_term_appears_in_source(clean_item["french"], source_text):
            continue
        clean_vocabulary.append(clean_item)
    return clean_vocabulary


def validate_developer_vocabulary(vocabulary):
    if not isinstance(vocabulary, list) or len(vocabulary) > MAX_DEVELOPER_LIST_ITEMS:
        return None
    clean_vocabulary = []
    for item in vocabulary:
        if not isinstance(item, dict) or not AI_VOCABULARY_FIELDS <= set(item):
            continue
        if any(not isinstance(item[field], str) or not item[field].strip() for field in AI_VOCABULARY_FIELDS):
            continue
        clean_vocabulary.append({field: item[field].strip() for field in AI_VOCABULARY_FIELDS})
    return clean_vocabulary


def validate_developer_mode_result(result):
    if not isinstance(result, dict) or not DEVELOPER_MODE_FIELDS <= set(result):
        return None
    if not isinstance(result["translation"], str) or not result["translation"].strip():
        return None

    explicit_requirements = validate_string_list(result["explicit_requirements"], MAX_DEVELOPER_LIST_ITEMS)
    implementation_notes = validate_string_list(result["implementation_notes"], MAX_DEVELOPER_LIST_ITEMS)
    ambiguities = validate_string_list(result["ambiguities"], MAX_DEVELOPER_LIST_ITEMS)
    vocabulary = validate_developer_vocabulary(result["important_vocabulary"])
    if any(value is None for value in (explicit_requirements, implementation_notes, ambiguities, vocabulary)):
        return None

    return {
        "translation": result["translation"].strip(),
        "explicit_requirements": explicit_requirements,
        "implementation_notes": implementation_notes,
        "important_vocabulary": vocabulary,
        "ambiguities": ambiguities,
    }


def validate_ai_lookup_result(result):
    if not isinstance(result, dict) or set(result) != AI_LOOKUP_FIELDS:
        return None
    if any(not isinstance(result[field], str) or not result[field].strip() for field in ("english", "explanation")):
        return None
    business_context = result["business_context"]
    if business_context is not None and (not isinstance(business_context, str) or not business_context.strip()):
        return None
    return {
        "english": result["english"].strip(),
        "explanation": result["explanation"].strip(),
        "business_context": business_context.strip() if business_context else None,
    }


def build_translate_cache_key(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_local_ollama_url(url):
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme != "http" or not parsed_url.hostname:
        return False
    if parsed_url.hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(parsed_url.hostname).is_loopback
    except ValueError:
        return False


def fetch_structured_ollama(system_prompt, text):
    if not is_local_ollama_url(OLLAMA_URL):
        return None, "Local Ollama is unavailable. Configure OLLAMA_URL with a loopback address."

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
    }
    http_request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(http_request, timeout=OLLAMA_TIMEOUT) as response:
            raw_response = response.read()
    except (OSError, TimeoutError, socket.timeout, urllib.error.URLError):
        return None, "Local Ollama is unavailable. Start Ollama and make sure the configured model is installed."

    try:
        response_data = json.loads(raw_response.decode("utf-8"))
        parsed_result = json.loads(response_data["message"]["content"])
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        return None, "Local Ollama returned an invalid structured response. Please try again."

    return parsed_result, None


def fetch_translate_explain(text):
    system_prompt = (
        "You are a French workplace-language assistant for English-speaking software developers. "
        "Translate French text naturally and explain only what is supported by the text. "
        "Return JSON only, with exactly these keys: natural_english_translation, "
        "line_translations, plain_english_meaning, business_crm_context, important_vocabulary, "
        "developer_interpretation. "
        "natural_english_translation must be a complete, faithful natural English translation of every meaningful "
        "part of the supplied French source. It is a translation, not a summary: do not omit later sentences, "
        "paragraphs, or details. plain_english_meaning must be a concise non-empty English explanation or summary "
        "of the overall text, separate from the translation. "
        "line_translations must be null unless the source is a short multi-line list of UI labels, statuses, or "
        "workflow actions. For such a list, return one object per non-empty source line, in the same order, with "
        "exactly french and english fields. Each french field must reproduce its source line; do not add entries. "
        "When the source is such a list, do not omit line_translations. "
        "business_crm_context must be a concise English string when meaningful workplace, CRM, sales, or product "
        "context is present; otherwise null. important_vocabulary must be a JSON array of at most 12 useful terms "
        "extracted from the supplied French source only. Every french term must occur in the source; do not invent "
        "related vocabulary or add topic-relevant terms that do not occur. Each term must have exactly french, "
        "english, and explanation as non-empty strings. "
        "developer_interpretation must be a concise English string only when the text implies software behavior, "
        "workflow, status handling, permissions, UI behavior, or implementation requirements; otherwise null. "
        "Do not invent business context, requirements, policies, names, or facts not present in the source text."
    )
    parsed_result, error = fetch_structured_ollama(system_prompt, text)
    if error:
        return None, error

    validated_result = validate_translate_explain_result(parsed_result, text)
    if validated_result is None:
        return None, "Local Ollama returned an invalid structured response. Please try again."

    return validated_result, None


def get_translate_explain(text):
    cache_key = build_translate_cache_key(text)
    cached_result = TRANSLATE_EXPLAIN_CACHE.get(cache_key)
    if cached_result is not None:
        return cached_result, None

    result, error = fetch_translate_explain(text)
    if result is not None:
        if len(TRANSLATE_EXPLAIN_CACHE) >= TRANSLATE_CACHE_LIMIT:
            TRANSLATE_EXPLAIN_CACHE.pop(next(iter(TRANSLATE_EXPLAIN_CACHE)))
        TRANSLATE_EXPLAIN_CACHE[cache_key] = result
    return result, error


def fetch_ai_lookup(query):
    system_prompt = (
        "You are a French workplace-language assistant for English-speaking software developers. "
        "Give a concise lookup for the supplied French word or short phrase. Return JSON only with exactly these keys: "
        "english, explanation, business_context. english and explanation must be concise non-empty English strings. "
        "business_context must be a concise English string only when meaningful workplace, CRM, sales, product, or "
        "software context is supported; otherwise null. Do not invent organization-specific meanings, policies, names, "
        "or facts. Do not provide examples, related terms, quizzes, or a full document translation."
    )
    parsed_result, error = fetch_structured_ollama(system_prompt, query)
    if error:
        return None, error

    validated_result = validate_ai_lookup_result(parsed_result)
    if validated_result is None:
        return None, "Local Ollama returned an invalid structured response. Please try again."

    return validated_result, None


def fetch_developer_mode(text):
    system_prompt = (
        "You are a French requirements interpretation assistant for English-speaking software developers. "
        "Translate the French source naturally. Return JSON only with exactly these keys: translation, "
        "explicit_requirements, implementation_notes, important_vocabulary, ambiguities. "
        "translation must be a concise non-empty English string. explicit_requirements must contain only rules "
        "the French source explicitly states or directly expresses linguistically. Never add implementation assumptions "
        "there. implementation_notes must contain only reasonable developer-oriented interpretations or suggestions; "
        "they are not confirmed requirements. ambiguities must contain only source-specific questions that need "
        "clarification, not generic filler. important_vocabulary must contain at most 12 objects with exactly french, "
        "english, and explanation as non-empty strings. Each array must contain at most 12 concise strings or objects "
        "and may be empty when the source does not support meaningful content for that section. "
        "Never invent company policies, permissions, statuses, workflows, or facts. Surface uncertainty in ambiguities."
    )
    parsed_result, error = fetch_structured_ollama(system_prompt, text)
    if error:
        return None, error

    validated_result = validate_developer_mode_result(parsed_result)
    if validated_result is None:
        return None, "Local Ollama returned an invalid structured response. Please try again."
    return validated_result, None


@app.route("/", methods=["GET"])
def home():
    return render_template("index.html", static_asset_version=STATIC_ASSET_VERSION)


@app.route("/api/lookup", methods=["POST"])
def api_lookup():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("query"), str):
        return jsonify({"ok": False, "error": "Request must be JSON with a query string."}), 400

    query = payload["query"].strip()
    result = lookup_term(query)

    if result is not None:
        return jsonify({"ok": True, "query": query, "result": result, "kind": "glossary"})

    if not query:
        return jsonify({"ok": False, "query": query, "result": None}), 404
    if len(query) > MAX_LOOKUP_QUERY_LENGTH:
        return jsonify({"ok": False, "error": f"Lookup text must be {MAX_LOOKUP_QUERY_LENGTH} characters or fewer."}), 413

    ai_result, error = fetch_ai_lookup(query)
    if error:
        return jsonify({"ok": False, "query": query, "error": error}), 503 if "unavailable" in error else 502

    return jsonify(
        {
            "ok": True,
            "query": query,
            "kind": "ai",
            "result": {
                "term": query,
                "english": ai_result["english"],
                "literal_translation": "",
                "category": "AI-generated lookup",
                "explanation": ai_result["explanation"],
                "business_context": ai_result["business_context"] or "No specific workplace or CRM context identified.",
                "examples": [],
                "related_terms": [],
                "source": "AI-generated",
                "ai_generated": True,
            },
        }
    )


@app.route("/api/translate-explain", methods=["POST"])
def api_translate_explain():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        return jsonify({"ok": False, "error": "Request must be JSON with a text string."}), 400

    text = payload["text"].strip()
    if not text:
        return jsonify({"ok": False, "error": "Enter French text to translate and explain."}), 400
    if len(text) > MAX_TRANSLATE_TEXT_LENGTH:
        return jsonify({"ok": False, "error": f"Text must be {MAX_TRANSLATE_TEXT_LENGTH:,} characters or fewer."}), 413

    result, error = get_translate_explain(text)
    if error:
        return jsonify({"ok": False, "error": error}), 503 if "unavailable" in error else 502

    return jsonify({"ok": True, "result": result})


@app.route("/api/developer-mode", methods=["POST"])
def api_developer_mode():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        return jsonify({"ok": False, "error": "Request must be JSON with a text string."}), 400

    text = payload["text"].strip()
    if not text:
        return jsonify({"ok": False, "error": "Enter French text to interpret for development."}), 400
    if len(text) > MAX_TRANSLATE_TEXT_LENGTH:
        return jsonify({"ok": False, "error": f"Text must be {MAX_TRANSLATE_TEXT_LENGTH:,} characters or fewer."}), 413

    result, error = fetch_developer_mode(text)
    if error:
        return jsonify({"ok": False, "error": error}), 503 if "unavailable" in error else 502

    return jsonify({"ok": True, "result": result})


@app.route("/api/saved-terms", methods=["GET"])
def api_list_saved_terms():
    query = request.args.get("q", "").strip()
    source = request.args.get("source", "").strip()
    if len(query) > MAX_SAVED_TERM_LENGTH:
        return jsonify({"ok": False, "error": "Search text is too long."}), 400
    if source and source not in SAVED_TERM_SOURCES:
        return jsonify({"ok": False, "error": "Invalid source filter."}), 400

    try:
        terms, total = list_saved_terms(query=query, source=source)
    except (OSError, sqlite3.Error):
        return jsonify({"ok": False, "error": "Saved Terms storage is unavailable. Please try again."}), 503
    return jsonify({"ok": True, "terms": terms, "total": total})


@app.route("/api/saved-terms", methods=["POST"])
def api_save_term():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("kind") not in {"glossary", "ai_vocabulary"}:
        return jsonify({"ok": False, "error": "Request must identify a glossary term or AI vocabulary item."}), 400

    if payload["kind"] == "glossary":
        if set(payload) != {"kind", "term"}:
            return jsonify({"ok": False, "error": "Invalid glossary save request."}), 400
        saved_term = build_saved_term_from_glossary(payload["term"])
        if saved_term is None:
            return jsonify({"ok": False, "error": "The glossary term could not be saved."}), 400
    else:
        if set(payload) != {"kind", "french", "english", "explanation"}:
            return jsonify({"ok": False, "error": "Invalid AI vocabulary save request."}), 400
        saved_term = build_saved_term_from_ai(payload)
        if saved_term is None:
            return jsonify({"ok": False, "error": "The AI vocabulary item could not be saved."}), 400

    try:
        saved_id, created = save_term(saved_term)
    except (OSError, sqlite3.Error):
        return jsonify({"ok": False, "error": "Saved Terms storage is unavailable. Please try again."}), 503
    if not created:
        return jsonify({"ok": True, "saved": False, "message": "Already saved."})
    return jsonify({"ok": True, "saved": True, "id": saved_id, "message": "Saved."}), 201


@app.route("/api/saved-terms/status", methods=["POST"])
def api_saved_term_statuses():
    payload = request.get_json(silent=True)
    terms = payload.get("terms") if isinstance(payload, dict) else None
    if not isinstance(terms, list) or not 1 <= len(terms) <= MAX_SAVED_TERM_STATUS_ITEMS:
        return jsonify({"ok": False, "error": "Request must include up to 12 term strings."}), 400
    clean_terms = [validate_saved_text(term, limit=MAX_SAVED_TERM_LENGTH) for term in terms]
    if any(term is None for term in clean_terms):
        return jsonify({"ok": False, "error": "Request must include valid term strings."}), 400
    try:
        saved = get_saved_term_statuses(clean_terms)
    except (OSError, sqlite3.Error):
        return jsonify({"ok": False, "error": "Saved Terms storage is unavailable. Please try again."}), 503
    return jsonify({"ok": True, "saved": saved})


@app.route("/api/saved-terms/<term_id>", methods=["DELETE"])
def api_delete_saved_term(term_id):
    if not term_id.isdigit() or int(term_id) < 1:
        return jsonify({"ok": False, "error": "Invalid saved term id."}), 400
    term_id = int(term_id)
    try:
        deleted = delete_saved_term(term_id)
    except (OSError, sqlite3.Error):
        return jsonify({"ok": False, "error": "Saved Terms storage is unavailable. Please try again."}), 503
    if not deleted:
        return jsonify({"ok": False, "error": "Saved term not found."}), 404
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True)
