def test_healthz(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_preflight_allows_frontend_bearer_token(client):
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://ai.lihaichao.cn",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://ai.lihaichao.cn"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_cors_rejects_unknown_origin(client):
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://unknown.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
