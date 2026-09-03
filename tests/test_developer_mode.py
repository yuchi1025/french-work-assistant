import json
import socket

import pytest

import app as french_app


class FakeOllamaResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def valid_developer_result():
    return {
        "translation": "When a prospect is marked as outside the target, it must no longer appear in the active prospects list.",
        "explicit_requirements": [
            "A prospect marked as outside the target must not appear in the active prospects list."
        ],
        "implementation_notes": [
            "Consider applying the exclusion in the data query as well as the visible list."
        ],
        "important_vocabulary": [
            {
                "french": "hors cible",
                "english": "outside the target",
                "explanation": "A prospect does not match the intended target criteria.",
            }
        ],
        "ambiguities": [
            "Does the exclusion also apply to historical or archived prospect lists?"
        ],
    }


def mock_ollama(monkeypatch, result):
    payload = {"message": {"content": json.dumps(result)}}

    def fake_urlopen(request, timeout):
        return FakeOllamaResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(french_app.urllib.request, "urlopen", fake_urlopen)


@pytest.fixture
def developer_client(tmp_path):
    previous_path = french_app.app.config.get("SAVED_TERMS_DB_PATH")
    french_app.app.config["SAVED_TERMS_DB_PATH"] = str(tmp_path / "saved_terms.db")
    try:
        yield french_app.app.test_client()
    finally:
        if previous_path is None:
            french_app.app.config.pop("SAVED_TERMS_DB_PATH", None)
        else:
            french_app.app.config["SAVED_TERMS_DB_PATH"] = previous_path


def test_developer_mode_succeeds_and_separates_sections(monkeypatch, developer_client):
    mock_ollama(monkeypatch, valid_developer_result())

    response = developer_client.post(
        "/api/developer-mode",
        json={"text": "Lorsqu'un prospect est marqué comme hors cible, il ne doit plus apparaître dans la liste des prospects actifs."},
    )

    assert response.status_code == 200
    result = response.get_json()["result"]
    assert result["explicit_requirements"] == [
        "A prospect marked as outside the target must not appear in the active prospects list."
    ]
    assert result["implementation_notes"] == [
        "Consider applying the exclusion in the data query as well as the visible list."
    ]
    assert result["ambiguities"] == ["Does the exclusion also apply to historical or archived prospect lists?"]


def test_developer_mode_rejects_empty_and_invalid_requests(developer_client):
    assert developer_client.post("/api/developer-mode", json={"text": " "}).status_code == 400
    assert developer_client.post("/api/developer-mode", json={"text": ["not text"]}).status_code == 400


def test_developer_mode_rejects_excessive_input(developer_client):
    response = developer_client.post(
        "/api/developer-mode",
        json={"text": "a" * (french_app.MAX_TRANSLATE_TEXT_LENGTH + 1)},
    )

    assert response.status_code == 413


def test_developer_mode_rejects_malformed_ollama_json(monkeypatch, developer_client):
    def fake_urlopen(request, timeout):
        return FakeOllamaResponse(b'{"message": {"content": "not json"}}')

    monkeypatch.setattr(french_app.urllib.request, "urlopen", fake_urlopen)

    response = developer_client.post("/api/developer-mode", json={"text": "Le statut doit être visible."})

    assert response.status_code == 502
    assert "invalid structured response" in response.get_json()["error"]


def test_developer_mode_rejects_missing_or_empty_translation(monkeypatch, developer_client):
    result = valid_developer_result()
    result.pop("translation")
    mock_ollama(monkeypatch, result)

    assert developer_client.post("/api/developer-mode", json={"text": "Le statut doit être visible."}).status_code == 502

    result = valid_developer_result()
    result["translation"] = " "
    mock_ollama(monkeypatch, result)

    assert developer_client.post("/api/developer-mode", json={"text": "Le statut doit être visible."}).status_code == 502


def test_developer_mode_rejects_missing_conceptual_field(monkeypatch, developer_client):
    result = valid_developer_result()
    result.pop("ambiguities")
    mock_ollama(monkeypatch, result)

    response = developer_client.post("/api/developer-mode", json={"text": "Le statut doit être visible."})

    assert response.status_code == 502


def test_developer_mode_normalizes_short_requirement_strings_and_ignores_extra_fields(monkeypatch, developer_client):
    result = valid_developer_result()
    result.update(
        {
            "translation": "Fix: Click event: start date.",
            "explicit_requirements": "Clicking an event should use its start date.",
            "implementation_notes": "Confirm where the start date should be displayed.",
            "important_vocabulary": [],
            "ambiguities": [],
            "model_note": "Harmless extra metadata.",
        }
    )
    mock_ollama(monkeypatch, result)

    response = developer_client.post(
        "/api/developer-mode",
        json={"text": "Fix: Cliquez sur événement: date de début"},
    )

    assert response.status_code == 200
    data = response.get_json()["result"]
    assert data["explicit_requirements"] == ["Clicking an event should use its start date."]
    assert data["implementation_notes"] == ["Confirm where the start date should be displayed."]
    assert data["ambiguities"] == []


def test_developer_mode_accepts_empty_optional_sections(monkeypatch, developer_client):
    result = valid_developer_result()
    result["implementation_notes"] = []
    result["ambiguities"] = []
    result["important_vocabulary"] = []
    mock_ollama(monkeypatch, result)

    response = developer_client.post("/api/developer-mode", json={"text": "Le statut doit être visible."})

    assert response.status_code == 200
    data = response.get_json()["result"]
    assert data["implementation_notes"] == []
    assert data["ambiguities"] == []


def test_developer_mode_filters_malformed_vocabulary_entries(monkeypatch, developer_client):
    result = valid_developer_result()
    result["important_vocabulary"].append({"french": "incomplet", "english": "incomplete"})
    result["important_vocabulary"].append("not an object")
    mock_ollama(monkeypatch, result)

    response = developer_client.post("/api/developer-mode", json={"text": "Le statut doit être visible."})

    assert response.status_code == 200
    assert response.get_json()["result"]["important_vocabulary"] == [valid_developer_result()["important_vocabulary"][0]]


def test_developer_mode_handles_ollama_unavailable_and_timeout(monkeypatch, developer_client):
    def unavailable_urlopen(request, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(french_app.urllib.request, "urlopen", unavailable_urlopen)
    assert developer_client.post("/api/developer-mode", json={"text": "Le statut doit être visible."}).status_code == 503

    def timeout_urlopen(request, timeout):
        raise socket.timeout("timed out")

    monkeypatch.setattr(french_app.urllib.request, "urlopen", timeout_urlopen)
    assert developer_client.post("/api/developer-mode", json={"text": "Le statut doit être visible."}).status_code == 503


def test_developer_vocabulary_can_be_saved_individually(monkeypatch, developer_client):
    mock_ollama(monkeypatch, valid_developer_result())
    response = developer_client.post("/api/developer-mode", json={"text": "Le statut doit être visible."})
    vocabulary = response.get_json()["result"]["important_vocabulary"][0]

    saved = developer_client.post("/api/saved-terms", json={"kind": "ai_vocabulary", **vocabulary})

    assert saved.status_code == 201
    term = developer_client.get("/api/saved-terms").get_json()["terms"][0]
    assert term["french"] == "hors cible"
    assert term["source"] == "AI"
