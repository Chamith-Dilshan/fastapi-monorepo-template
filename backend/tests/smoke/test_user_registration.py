import pytest


@pytest.mark.asyncio
async def test_register_user_defaults_to_user_role_and_unverified(client, faker):
    payload = {
        "email": faker.unique.email(),
        "password": "StrongP@ssw0rd!",
        "first_name": faker.first_name(),
        "last_name": faker.last_name(),
    }

    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code in (200, 201), response.text
    body = response.json()
    # These two are the actual security property this test exists to
    # guard: nothing in UserCreateRequest lets a signup pick its own role
    # or arrive pre-verified.
    assert body["role"] == "user"
    assert body["is_verified"] is False


@pytest.mark.asyncio
async def test_register_duplicate_email_is_conflict(client, faker):
    payload = {
        "email": faker.unique.email(),
        "password": "StrongP@ssw0rd!",
        "first_name": faker.first_name(),
        "last_name": faker.last_name(),
    }
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code in (200, 201), first.text

    second = await client.post("/api/v1/auth/register", json=payload)

    assert second.status_code == 409
    body = second.json()
    # Exercises the exception_handlers.py envelope end to end, not just
    # the status code.
    assert body["error"]["code"] == "conflict"
    assert "request_id" in body["error"]
