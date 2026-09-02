import sqlite3

import pytest

import app as french_app


@pytest.fixture
def saved_terms_client(tmp_path):
    database_path = tmp_path / "saved_terms.db"
    previous_path = french_app.app.config.get("SAVED_TERMS_DB_PATH")
    french_app.app.config["SAVED_TERMS_DB_PATH"] = str(database_path)
    try:
        yield french_app.app.test_client(), database_path
    finally:
        if previous_path is None:
            french_app.app.config.pop("SAVED_TERMS_DB_PATH", None)
        else:
            french_app.app.config["SAVED_TERMS_DB_PATH"] = previous_path


def save_glossary_term(client, term):
    return client.post("/api/saved-terms", json={"kind": "glossary", "term": term})


def test_database_initialization_uses_temporary_path(saved_terms_client):
    _, database_path = saved_terms_client

    french_app.init_saved_terms_db()

    assert database_path.exists()
    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(saved_terms)")}
    assert {"normalized_term", "french", "english", "source", "saved_at"} <= columns
    assert french_app.get_saved_terms_db_path() == database_path


def test_save_glossary_term_resolves_backend_entry(saved_terms_client):
    client, _ = saved_terms_client

    response = save_glossary_term(client, "prospect")

    assert response.status_code == 201
    assert response.get_json()["saved"] is True
    listed = client.get("/api/saved-terms").get_json()["terms"]
    assert listed[0]["french"] == "prospect"
    assert listed[0]["english"] == "prospect or lead"
    assert listed[0]["source"] == "CRM"


def test_save_ai_vocabulary_term(saved_terms_client):
    client, _ = saved_terms_client

    response = client.post(
        "/api/saved-terms",
        json={
            "kind": "ai_vocabulary",
            "french": "comportement attendu",
            "english": "expected behavior",
            "explanation": "A generic phrase about how a product should behave.",
        },
    )

    assert response.status_code == 201
    term = client.get("/api/saved-terms").get_json()["terms"][0]
    assert term["source"] == "AI"
    assert term["literal_translation"] == ""
    assert term["category"] == ""


def test_save_ai_lookup_result(saved_terms_client):
    client, _ = saved_terms_client

    response = client.post(
        "/api/saved-terms",
        json={
            "kind": "ai_vocabulary",
            "french": "archiver",
            "english": "to archive",
            "explanation": "A generic action that moves an item out of an active view.",
        },
    )

    assert response.status_code == 201
    term = client.get("/api/saved-terms").get_json()["terms"][0]
    assert term["french"] == "archiver"
    assert term["source"] == "AI"


def test_duplicate_normalized_terms_are_not_inserted(saved_terms_client):
    client, _ = saved_terms_client

    assert save_glossary_term(client, "NRP").status_code == 201
    response = save_glossary_term(client, "nrp")

    assert response.status_code == 200
    assert response.get_json()["saved"] is False
    assert client.get("/api/saved-terms").get_json()["total"] == 1


def test_list_saved_terms_newest_first_and_search(saved_terms_client):
    client, _ = saved_terms_client
    save_glossary_term(client, "prospect")
    save_glossary_term(client, "devis")

    listed = client.get("/api/saved-terms").get_json()

    assert [term["french"] for term in listed["terms"]] == ["devis", "prospect"]
    assert client.get("/api/saved-terms?q=prospect").get_json()["terms"][0]["french"] == "prospect"
    assert client.get("/api/saved-terms?q=quote").get_json()["terms"][0]["french"] == "devis"


def test_list_saved_terms_filters_by_source(saved_terms_client):
    client, _ = saved_terms_client
    save_glossary_term(client, "rendez-vous")
    save_glossary_term(client, "prospect")
    client.post(
        "/api/saved-terms",
        json={
            "kind": "ai_vocabulary",
            "french": "statut temporaire",
            "english": "temporary status",
            "explanation": "A fictional vocabulary item for an automated test.",
        },
    )

    assert client.get("/api/saved-terms?source=Workplace").get_json()["terms"][0]["french"] == "rendez-vous"
    assert client.get("/api/saved-terms?source=CRM").get_json()["terms"][0]["french"] == "prospect"
    assert client.get("/api/saved-terms?source=AI").get_json()["terms"][0]["french"] == "statut temporaire"


def test_delete_saved_term_only_removes_personal_history(saved_terms_client):
    client, _ = saved_terms_client
    saved_id = save_glossary_term(client, "prospect").get_json()["id"]

    response = client.delete(f"/api/saved-terms/{saved_id}")

    assert response.status_code == 200
    assert client.get("/api/saved-terms").get_json()["total"] == 0
    assert french_app.lookup_term("prospect")["term"] == "prospect"


def test_invalid_save_and_delete_requests_are_rejected(saved_terms_client):
    client, _ = saved_terms_client

    assert client.post("/api/saved-terms", json={"kind": "glossary", "term": "unknown"}).status_code == 400
    assert client.post(
        "/api/saved-terms",
        json={"kind": "glossary", "term": "prospect", "english": "forged value"},
    ).status_code == 400
    assert client.post("/api/saved-terms", json={"kind": "ai_vocabulary", "french": "only"}).status_code == 400
    assert client.post("/api/saved-terms", json={"kind": "unknown"}).status_code == 400
    assert client.get("/api/saved-terms?source=Unknown").status_code == 400
    assert client.delete("/api/saved-terms/not-an-id").status_code == 400
    assert client.delete("/api/saved-terms/999").status_code == 404


def test_saved_terms_storage_errors_are_generic(monkeypatch, saved_terms_client):
    client, _ = saved_terms_client

    def raise_storage_error(*args, **kwargs):
        raise sqlite3.OperationalError("private filesystem detail")

    monkeypatch.setattr(french_app, "list_saved_terms", raise_storage_error)
    response = client.get("/api/saved-terms")
    assert response.status_code == 503
    assert response.get_json()["error"] == "Saved Terms storage is unavailable. Please try again."

    monkeypatch.setattr(french_app, "save_term", raise_storage_error)
    response = save_glossary_term(client, "prospect")
    assert response.status_code == 503
    assert "private filesystem detail" not in response.get_json()["error"]

    monkeypatch.setattr(french_app, "delete_saved_term", raise_storage_error)
    response = client.delete("/api/saved-terms/1")
    assert response.status_code == 503
