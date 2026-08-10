import hashlib
import ipaddress
import json
import os
import re
import socket
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Flask, jsonify, render_template, request


app = Flask(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
BUILT_IN_GLOSSARY_PATHS = (
    DATA_DIR / "workplace_glossary.json",
    DATA_DIR / "crm_glossary.json",
)
CUSTOM_GLOSSARY_PATH = DATA_DIR / "custom_glossary.json"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3")
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "15m")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "45"))
MAX_TRANSLATE_TEXT_LENGTH = 6000
TRANSLATE_CACHE_LIMIT = 64
TRANSLATE_EXPLAIN_CACHE = {}

REQUIRED_FIELDS = (
    "term",
    "english",
    "literal",
    "category",
    "explanation",
    "business_context",
    "example_fr",
    "example_en",
    "related_terms",
)

AI_REQUIRED_FIELDS = {
    "natural_english_translation",
    "plain_english_meaning",
    "business_crm_context",
    "important_vocabulary",
    "developer_interpretation",
}
AI_VOCABULARY_FIELDS = {"french", "english", "explanation"}


def normalize_text(value):
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    text = text.replace("’", "'")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", text)


def normalize_entry(raw_entry, source):
    entry = {field: raw_entry.get(field, "") for field in REQUIRED_FIELDS}
    entry["term"] = str(entry["term"]).strip()
    entry["english"] = str(entry["english"]).strip()
    entry["literal"] = str(entry["literal"]).strip()
    entry["category"] = str(entry["category"]).strip()
    entry["explanation"] = str(entry["explanation"]).strip()
    entry["business_context"] = str(entry["business_context"]).strip()
    entry["example_fr"] = str(entry["example_fr"]).strip()
    entry["example_en"] = str(entry["example_en"]).strip()
    entry["related_terms"] = [str(term).strip() for term in entry["related_terms"] if str(term).strip()]
    entry["source"] = source
    entry["search_terms"] = build_search_terms(entry)
    return entry


def build_search_terms(entry):
    candidates = [
        entry["term"],
        entry["english"],
        entry["literal"],
        *entry["related_terms"],
    ]
    return sorted({normalize_text(candidate) for candidate in candidates if normalize_text(candidate)})


def load_glossary_file(path, source):
    with path.open(encoding="utf-8") as glossary_file:
        raw_entries = json.load(glossary_file)

    return [normalize_entry(raw_entry, source) for raw_entry in raw_entries if raw_entry.get("term")]


def load_glossary(custom_path=CUSTOM_GLOSSARY_PATH):
    entries = []
    for path in BUILT_IN_GLOSSARY_PATHS:
        entries.extend(load_glossary_file(path, "built-in"))

    if custom_path and custom_path.exists():
        entries.extend(load_glossary_file(custom_path, "custom"))

    return entries


def lookup_term(query, entries=None):
    normalized_query = normalize_text(query)
    if not normalized_query:
        return None

    glossary_entries = entries if entries is not None else load_glossary()

    for entry in glossary_entries:
        if normalized_query == normalize_text(entry["term"]):
            return entry

    for entry in glossary_entries:
        if normalized_query in entry["search_terms"]:
            return entry

    return None


def validate_translate_explain_result(result):
    if not isinstance(result, dict) or set(result) != AI_REQUIRED_FIELDS:
        return None

    for field in ("natural_english_translation", "plain_english_meaning"):
        if not isinstance(result[field], str) or not result[field].strip():
            return None

    for field in ("business_crm_context", "developer_interpretation"):
        if result[field] is not None and (not isinstance(result[field], str) or not result[field].strip()):
            return None

    vocabulary = result["important_vocabulary"]
    if not isinstance(vocabulary, list) or len(vocabulary) > 12:
        return None

    clean_vocabulary = []
    for item in vocabulary:
        if not isinstance(item, dict) or set(item) != AI_VOCABULARY_FIELDS:
            return None
        if any(not isinstance(item[field], str) or not item[field].strip() for field in AI_VOCABULARY_FIELDS):
            return None
        clean_vocabulary.append({field: item[field].strip() for field in AI_VOCABULARY_FIELDS})

    return {
        "natural_english_translation": result["natural_english_translation"].strip(),
        "plain_english_meaning": result["plain_english_meaning"].strip(),
        "business_crm_context": result["business_crm_context"].strip() if result["business_crm_context"] else None,
        "important_vocabulary": clean_vocabulary,
        "developer_interpretation": result["developer_interpretation"].strip() if result["developer_interpretation"] else None,
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


def fetch_translate_explain(text):
    if not is_local_ollama_url(OLLAMA_URL):
        return None, "Local Ollama is unavailable. Configure OLLAMA_URL with a loopback address."

    system_prompt = (
        "You are a French workplace-language assistant for English-speaking software developers. "
        "Translate French text naturally and explain only what is supported by the text. "
        "Return JSON only, with exactly these keys: natural_english_translation, "
        "plain_english_meaning, business_crm_context, important_vocabulary, developer_interpretation. "
        "natural_english_translation and plain_english_meaning must be concise non-empty English strings. "
        "business_crm_context must be a concise English string when meaningful workplace, CRM, sales, or product "
        "context is present; otherwise null. important_vocabulary must be a JSON array of at most 12 useful terms. "
        "Each term must have exactly french, english, and explanation as non-empty strings. "
        "developer_interpretation must be a concise English string only when the text implies software behavior, "
        "workflow, status handling, permissions, UI behavior, or implementation requirements; otherwise null. "
        "Do not invent business context, requirements, policies, names, or facts not present in the source text."
    )
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
            raw_response = response.read().decode("utf-8")
    except (OSError, TimeoutError, socket.timeout, urllib.error.URLError):
        return None, "Local Ollama is unavailable. Start Ollama and make sure the configured model is installed."

    try:
        response_data = json.loads(raw_response)
        parsed_result = json.loads(response_data["message"]["content"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return None, "Local Ollama returned an invalid structured response. Please try again."

    validated_result = validate_translate_explain_result(parsed_result)
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


@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@app.route("/api/lookup", methods=["POST"])
def api_lookup():
    payload = request.get_json(silent=True) or {}
    query = payload.get("query", "")
    result = lookup_term(query)

    if result is None:
        return jsonify({"ok": False, "query": str(query).strip(), "result": None}), 404

    return jsonify({"ok": True, "query": str(query).strip(), "result": result})


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


if __name__ == "__main__":
    app.run(debug=True)
