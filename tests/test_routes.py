import app as french_app


def test_home_page_loads():
    client = french_app.app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"French Work Assistant" in response.data
    assert b"Quick Lookup" in response.data
    assert b"Developer Mode" in response.data


def test_lookup_api_returns_result():
    client = french_app.app.test_client()

    response = client.post("/api/lookup", json={"query": "prospect"})

    assert response.status_code == 200
    assert response.get_json()["result"]["term"] == "prospect"
    assert response.get_json()["result"]["source"] == "CRM"


def test_lookup_api_returns_not_found():
    client = french_app.app.test_client()

    response = client.post("/api/lookup", json={"query": "unknown"})

    assert response.status_code == 404
    assert response.get_json()["ok"] is False
