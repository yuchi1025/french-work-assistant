import json
import socket

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


def valid_result():
    return {
        "natural_english_translation": "The prospect did not respond, so they should be called again later.",
        "plain_english_meaning": "The sales lead has not replied and needs a future follow-up.",
        "business_crm_context": "This describes a CRM follow-up action for a prospect.",
        "important_vocabulary": [
            {
                "french": "prospect",
                "english": "sales lead",
                "explanation": "A potential customer who has not become a client yet.",
            }
        ],
        "developer_interpretation": None,
    }


def mock_ollama(monkeypatch, result):
    payload = {"message": {"content": json.dumps(result)}}

    def fake_urlopen(request, timeout):
        return FakeOllamaResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(french_app.urllib.request, "urlopen", fake_urlopen)
    french_app.TRANSLATE_EXPLAIN_CACHE.clear()


def test_translate_explain_succeeds_with_mocked_ollama(monkeypatch):
    mock_ollama(monkeypatch, valid_result())
    client = french_app.app.test_client()

    response = client.post(
        "/api/translate-explain",
        json={"text": "Le prospect n'a pas repondu, il faudra le rappeler ulterieurement."},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["result"]["important_vocabulary"][0]["french"] == "prospect"


def test_translate_explain_rejects_empty_input():
    client = french_app.app.test_client()

    response = client.post("/api/translate-explain", json={"text": "   "})

    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_translate_explain_rejects_invalid_request():
    client = french_app.app.test_client()

    response = client.post("/api/translate-explain", json={"text": ["not", "text"]})

    assert response.status_code == 400
    assert response.get_json()["error"] == "Request must be JSON with a text string."


def test_translate_explain_rejects_excessive_input():
    client = french_app.app.test_client()

    response = client.post("/api/translate-explain", json={"text": "a" * (french_app.MAX_TRANSLATE_TEXT_LENGTH + 1)})

    assert response.status_code == 413
    assert "6,000" in response.get_json()["error"]


def test_translate_explain_rejects_malformed_ollama_json(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeOllamaResponse(b'{"message": {"content": "not json"}}')

    monkeypatch.setattr(french_app.urllib.request, "urlopen", fake_urlopen)
    french_app.TRANSLATE_EXPLAIN_CACHE.clear()
    client = french_app.app.test_client()

    response = client.post("/api/translate-explain", json={"text": "Planifier un rendez-vous."})

    assert response.status_code == 502
    assert "invalid structured response" in response.get_json()["error"]


def test_translate_explain_rejects_invalid_ollama_encoding(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeOllamaResponse(b"\xff")

    monkeypatch.setattr(french_app.urllib.request, "urlopen", fake_urlopen)
    french_app.TRANSLATE_EXPLAIN_CACHE.clear()
    client = french_app.app.test_client()

    response = client.post("/api/translate-explain", json={"text": "Planifier un rendez-vous."})

    assert response.status_code == 502
    assert "invalid structured response" in response.get_json()["error"]


def test_translate_explain_rejects_missing_required_ai_fields(monkeypatch):
    result = valid_result()
    result.pop("developer_interpretation")
    mock_ollama(monkeypatch, result)
    client = french_app.app.test_client()

    response = client.post("/api/translate-explain", json={"text": "Planifier un rendez-vous."})

    assert response.status_code == 502


def test_translate_explain_rejects_wrong_ai_field_types(monkeypatch):
    result = valid_result()
    result["important_vocabulary"] = "prospect"
    mock_ollama(monkeypatch, result)
    client = french_app.app.test_client()

    response = client.post("/api/translate-explain", json={"text": "Planifier un rendez-vous."})

    assert response.status_code == 502


def test_translate_explain_handles_ollama_unavailable(monkeypatch):
    def fake_urlopen(request, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(french_app.urllib.request, "urlopen", fake_urlopen)
    french_app.TRANSLATE_EXPLAIN_CACHE.clear()
    client = french_app.app.test_client()

    response = client.post("/api/translate-explain", json={"text": "Planifier un rendez-vous."})

    assert response.status_code == 503
    assert "Local Ollama is unavailable" in response.get_json()["error"]


def test_translate_explain_handles_ollama_timeout(monkeypatch):
    def fake_urlopen(request, timeout):
        raise socket.timeout("timed out")

    monkeypatch.setattr(french_app.urllib.request, "urlopen", fake_urlopen)
    french_app.TRANSLATE_EXPLAIN_CACHE.clear()
    client = french_app.app.test_client()

    response = client.post("/api/translate-explain", json={"text": "Planifier un rendez-vous."})

    assert response.status_code == 503
    assert "Local Ollama is unavailable" in response.get_json()["error"]


def test_translate_explain_rejects_non_local_ollama_url(monkeypatch):
    monkeypatch.setattr(french_app, "OLLAMA_URL", "https://example.invalid/api/chat")
    french_app.TRANSLATE_EXPLAIN_CACHE.clear()
    client = french_app.app.test_client()

    response = client.post("/api/translate-explain", json={"text": "Planifier un rendez-vous."})

    assert response.status_code == 503
    assert "loopback address" in response.get_json()["error"]
