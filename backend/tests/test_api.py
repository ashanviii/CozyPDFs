from fastapi.testclient import TestClient


def test_health(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_me_sets_identity_cookie(client: TestClient):
    response = client.get("/api/me")
    assert response.status_code == 200
    assert "identity_id" in response.json()
    assert "cozy_identity" in response.cookies


def test_me_reuses_identity_across_requests(client: TestClient):
    first = client.get("/api/me").json()
    second = client.get("/api/me").json()
    assert first["identity_id"] == second["identity_id"]


def test_me_issues_new_identity_for_a_fresh_client(app):
    client_a = TestClient(app)
    client_b = TestClient(app)

    identity_a = client_a.get("/api/me").json()["identity_id"]
    identity_b = client_b.get("/api/me").json()["identity_id"]

    assert identity_a != identity_b
