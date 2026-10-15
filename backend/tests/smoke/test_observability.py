import pytest


@pytest.mark.asyncio
async def test_a_request_id_is_generated_and_returned(client):
    response = await client.get("/health")
    assert len(response.headers["x-request-id"]) == 32


@pytest.mark.asyncio
async def test_an_incoming_request_id_is_kept_and_appears_in_error_bodies(client):
    response = await client.get(
        "/api/v1/auth/me", headers={"X-Request-ID": "trace-me-1"}
    )
    assert response.status_code == 401
    assert response.headers["x-request-id"] == "trace-me-1"
    assert response.json()["error"]["request_id"] == "trace-me-1"


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_text(client):
    await client.get("/health")
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "http_request" in response.text


@pytest.mark.asyncio
async def test_metrics_is_hidden_from_the_openapi_schema(client):
    schema = (await client.get("/openapi.json")).json()
    assert "/metrics" not in schema["paths"]


@pytest.mark.asyncio
async def test_garbage_bearer_token_is_a_401_envelope(client):
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer nonsense"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
