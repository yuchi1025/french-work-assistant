import json
import re
import unicodedata
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


if __name__ == "__main__":
    app.run(debug=True)
