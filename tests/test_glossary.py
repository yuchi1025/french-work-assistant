import json

import pytest

import app as french_app


def glossary_entry(term, english="generic English", related_terms=None):
    return {
        "term": term,
        "english": english,
        "literal_translation": "generic literal translation",
        "category": "Test category",
        "explanation": "A fictional definition used only for automated tests.",
        "business_context": "Generic fictional context with no real organization or customer information.",
        "examples": [{"french": f"Exemple pour {term}.", "english": f"Example for {term}."}],
        "related_terms": related_terms or [],
    }


def write_glossary(path, entries):
    path.write_text(json.dumps(entries), encoding="utf-8")


def test_loads_multiple_public_glossaries_with_source_metadata():
    entries = french_app.load_glossary(custom_path=None)
    source_by_term = {entry["term"]: entry["source"] for entry in entries}

    assert source_by_term["rendez-vous"] == "Workplace"
    assert source_by_term["prospect"] == "CRM"
    assert all(entry["domain"] == entry["source"] for entry in entries)
    assert all("literal_translation" in entry and "examples" in entry for entry in entries)


def test_missing_custom_glossary_does_not_break_loading(tmp_path):
    entries = french_app.load_glossary(custom_path=tmp_path / "custom_glossary.json")

    assert entries
    assert all(entry["source"] in {"Workplace", "CRM"} for entry in entries)


def test_valid_temporary_custom_glossary_loads(tmp_path):
    custom_path = tmp_path / "custom_glossary.json"
    write_glossary(custom_path, [glossary_entry("private workflow label")])

    entries = french_app.load_glossary(custom_path=custom_path)
    result = french_app.lookup_term("private workflow label", entries=entries)

    assert result["source"] == "Custom"
    assert result["term"] == "private workflow label"


def test_malformed_custom_glossary_has_generic_error(tmp_path):
    custom_path = tmp_path / "custom_glossary.json"
    custom_path.write_text("{ broken private content", encoding="utf-8")

    with pytest.raises(french_app.GlossaryValidationError) as error:
        french_app.load_glossary(custom_path=custom_path)

    assert str(error.value) == "Custom glossary is invalid. Check its JSON structure and schema."
    assert "private content" not in str(error.value)


def test_malformed_public_glossary_fails_clearly(tmp_path):
    glossary_path = tmp_path / "crm_glossary.json"
    glossary_path.write_text("{", encoding="utf-8")

    with pytest.raises(french_app.GlossaryValidationError, match="CRM glossary could not be loaded"):
        french_app.load_glossary_file(glossary_path, "CRM", 2)


def test_public_glossary_requires_a_top_level_array(tmp_path):
    glossary_path = tmp_path / "crm_glossary.json"
    glossary_path.write_text(json.dumps({"term": "not an array"}), encoding="utf-8")

    with pytest.raises(french_app.GlossaryValidationError, match="must contain a JSON array"):
        french_app.load_glossary_file(glossary_path, "CRM", 2)


def test_duplicate_normalized_terms_in_one_glossary_are_rejected(tmp_path):
    glossary_path = tmp_path / "crm_glossary.json"
    write_glossary(glossary_path, [glossary_entry("Pré-étude"), glossary_entry("pre-etude")])

    with pytest.raises(french_app.GlossaryValidationError, match="duplicate normalized terms"):
        french_app.load_glossary_file(glossary_path, "CRM", 2)


def test_invalid_entry_shape_is_rejected(tmp_path):
    glossary_path = tmp_path / "workplace_glossary.json"
    write_glossary(glossary_path, [{"term": "incomplete"}])

    with pytest.raises(french_app.GlossaryValidationError, match="invalid english field"):
        french_app.load_glossary_file(glossary_path, "Workplace", 1)


def test_malformed_examples_are_rejected(tmp_path):
    glossary_path = tmp_path / "crm_glossary.json"
    invalid_entry = glossary_entry("test term")
    invalid_entry["examples"] = [{"french": "French only"}]
    write_glossary(glossary_path, [invalid_entry])

    with pytest.raises(french_app.GlossaryValidationError, match="invalid example"):
        french_app.load_glossary_file(glossary_path, "CRM", 2)


def test_malformed_related_terms_are_rejected(tmp_path):
    glossary_path = tmp_path / "crm_glossary.json"
    invalid_entry = glossary_entry("test term")
    invalid_entry["related_terms"] = "not a list"
    write_glossary(glossary_path, [invalid_entry])

    with pytest.raises(french_app.GlossaryValidationError, match="invalid related_terms"):
        french_app.load_glossary_file(glossary_path, "CRM", 2)


def test_custom_precedence_over_crm_and_workplace(tmp_path):
    workplace_path = tmp_path / "workplace.json"
    crm_path = tmp_path / "crm.json"
    custom_path = tmp_path / "custom.json"
    write_glossary(workplace_path, [glossary_entry("shared term", "workplace meaning")])
    write_glossary(crm_path, [glossary_entry("shared term", "CRM meaning")])
    write_glossary(custom_path, [glossary_entry("shared term", "custom meaning")])

    entries = [
        *french_app.load_glossary_file(workplace_path, "Workplace", 1),
        *french_app.load_glossary_file(crm_path, "CRM", 2),
        *french_app.load_glossary_file(custom_path, "Custom", 3),
    ]
    result = french_app.lookup_term("shared term", entries=entries)

    assert result["source"] == "Custom"
    assert result["english"] == "custom meaning"
    assert french_app.lookup_term("shared term", entries=entries[:-1])["source"] == "CRM"


def test_french_english_case_accent_and_unicode_lookup():
    assert french_app.lookup_term("relance")["term"] == "relance"
    assert french_app.lookup_term("quote or estimate")["term"] == "devis"
    assert french_app.lookup_term("nrp")["term"] == "NRP"
    assert french_app.lookup_term("pre-etude")["term"] == "pré-étude"
    assert french_app.lookup_term("RÉLANCE")["term"] == "relance"


def test_abbreviation_and_related_term_lookup_behavior():
    assert french_app.lookup_term("RDV")["term"] == "RDV"
    related_result = french_app.lookup_term("devis")

    assert related_result["term"] == "devis"
    assert "relance" in french_app.lookup_term("prospect")["related_terms"]


def test_exact_matches_rank_before_partial_matches():
    entries = [
        french_app.normalize_entry(glossary_entry("prospection", "prospecting"), "CRM", 2, 1),
        french_app.normalize_entry(glossary_entry("prospect", "lead"), "CRM", 2, 2),
    ]

    assert french_app.lookup_term("prospect", entries=entries)["term"] == "prospect"
