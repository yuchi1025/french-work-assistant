import json

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


def ai_lookup_result():
    return {
        "english": "to archive",
        "explanation": "To move an item out of an active view while retaining it.",
        "business_context": "Often used for records that should no longer appear in an active list.",
    }


def mock_ollama(monkeypatch, result, requests=None):
    response_payload = {"message": {"content": json.dumps(result)}}

    def fake_urlopen(request, timeout):
        if requests is not None:
            requests.append(json.loads(request.data.decode("utf-8")))
        return FakeOllamaResponse(json.dumps(response_payload).encode("utf-8"))

    monkeypatch.setattr(french_app.urllib.request, "urlopen", fake_urlopen)


def test_home_page_loads():
    client = french_app.app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"French Work Assistant" in response.data
    assert b"Quick Lookup" in response.data
    assert b"Developer Mode" in response.data
    assert b"app.js?v=quick-lookup-ai-save-1" in response.data


def test_lookup_api_returns_glossary_result_without_ai_fallback(monkeypatch):
    def unexpected_fallback(query):
        raise AssertionError("AI fallback must not run for a glossary match")

    monkeypatch.setattr(french_app, "fetch_ai_lookup", unexpected_fallback)
    client = french_app.app.test_client()

    response = client.post("/api/lookup", json={"query": "prospect"})

    assert response.status_code == 200
    assert response.get_json()["result"]["term"] == "prospect"
    assert response.get_json()["result"]["source"] == "CRM"
    assert response.get_json()["kind"] == "glossary"


def test_lookup_api_uses_local_ai_fallback_for_unknown_term(monkeypatch):
    requests = []
    mock_ollama(monkeypatch, ai_lookup_result(), requests)
    client = french_app.app.test_client()

    response = client.post("/api/lookup", json={"query": "archiver"})

    assert response.status_code == 200
    data = response.get_json()
    assert data["kind"] == "ai"
    assert data["result"]["source"] == "AI-generated"
    assert data["result"]["ai_generated"] is True
    assert data["result"]["english"] == "to archive"
    assert requests[0]["messages"][1] == {"role": "user", "content": "archiver"}
    assert "concise lookup" in requests[0]["messages"][0]["content"]
    assert french_app.lookup_term("archiver") is None


def test_lookup_api_returns_local_ai_error_for_unknown_term(monkeypatch):
    def unavailable_fallback(query):
        return None, "Local Ollama is unavailable. Start Ollama and try again."

    monkeypatch.setattr(french_app, "fetch_ai_lookup", unavailable_fallback)
    client = french_app.app.test_client()

    response = client.post("/api/lookup", json={"query": "archiver"})

    assert response.status_code == 503
    assert "Local Ollama is unavailable" in response.get_json()["error"]


def test_lookup_api_rejects_invalid_ai_fallback_response(monkeypatch):
    result = ai_lookup_result()
    result.pop("business_context")
    mock_ollama(monkeypatch, result)
    client = french_app.app.test_client()

    response = client.post("/api/lookup", json={"query": "archiver"})

    assert response.status_code == 502
    assert "invalid structured response" in response.get_json()["error"]


def test_lookup_api_rejects_invalid_request_and_excessive_query():
    client = french_app.app.test_client()

    assert client.post("/api/lookup", json={"query": ["archiver"]}).status_code == 400
    response = client.post("/api/lookup", json={"query": "a" * (french_app.MAX_LOOKUP_QUERY_LENGTH + 1)})
    assert response.status_code == 413
