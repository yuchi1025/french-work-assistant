import json

import app as french_app


def test_load_glossary_includes_public_files():
    entries = french_app.load_glossary(custom_path=None)
    terms = {entry["term"] for entry in entries}

    assert "prospect" in terms
    assert "relance" in terms
    assert "pré-étude" in terms
    assert all(entry["source"] == "built-in" for entry in entries)


def test_exact_french_lookup():
    result = french_app.lookup_term("relance")

    assert result["term"] == "relance"
    assert result["english"] == "follow-up"


def test_case_insensitive_lookup():
    result = french_app.lookup_term("nrp")

    assert result["term"] == "NRP"
    assert result["category"] == "Call outcome"


def test_accent_insensitive_lookup():
    result = french_app.lookup_term("pre-etude")

    assert result["term"] == "pré-étude"


def test_english_lookup():
    result = french_app.lookup_term("quote or estimate")

    assert result["term"] == "devis"


def test_unknown_terms_return_none():
    assert french_app.lookup_term("not-a-real-public-glossary-term") is None


def test_missing_custom_glossary_does_not_break_loading(tmp_path):
    missing_custom_path = tmp_path / "custom_glossary.json"

    entries = french_app.load_glossary(custom_path=missing_custom_path)

    assert entries
    assert all(entry["source"] == "built-in" for entry in entries)


def test_temporary_custom_glossary_loads_in_tests(tmp_path):
    custom_path = tmp_path / "custom_glossary.json"
    custom_path.write_text(
        json.dumps(
            [
                {
                    "term": "fiche test",
                    "english": "test record",
                    "literal": "test sheet",
                    "category": "Custom",
                    "explanation": "A fictional record used only for automated tests.",
                    "business_context": "Generic test data with no real customer or company information.",
                    "example_fr": "La fiche test est visible dans le CRM de demonstration.",
                    "example_en": "The test record is visible in the demo CRM.",
                    "related_terms": ["record"],
                }
            ]
        ),
        encoding="utf-8",
    )

    entries = french_app.load_glossary(custom_path=custom_path)
    result = french_app.lookup_term("fiche test", entries=entries)

    assert result["term"] == "fiche test"
    assert result["source"] == "custom"
