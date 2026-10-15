import pytest

from app.core.audit import record_audit_event
from app.models.user import UserRole

URL = "/api/v1/admin/audit-logs"


async def _change_role(client, admin_headers, target, role="manager", **extra_headers):
    return await client.patch(
        f"/api/v1/users/{target.id}/role",
        headers={**admin_headers, **extra_headers},
        json={"role": role},
    )


@pytest.mark.asyncio
async def test_admins_see_entries_newest_first_with_the_actors_email(
    client, make_user, auth_headers
):
    admin = await make_user(role=UserRole.ADMIN)
    target = await make_user()
    headers = await auth_headers(admin)
    await _change_role(client, headers, target, "manager")
    await client.patch(
        f"/api/v1/users/{target.id}/status", headers=headers, json={"is_active": False}
    )

    body = (await client.get(URL, headers=headers)).json()

    assert body["total"] == 2
    assert [e["action"] for e in body["items"]] == [
        "user.deactivated",
        "user.role_changed",
    ]
    newest = body["items"][0]
    assert newest["actor_email"] == admin.email
    assert newest["resource_id"] == str(target.id)
    assert newest["before"] == {"is_active": True}
    assert newest["after"] == {"is_active": False}
    assert newest["request_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.USER, UserRole.GUEST])
async def test_only_admins_can_read_the_audit_log(
    client, make_user, auth_headers, role
):
    actor = await make_user(role=role)
    response = await client.get(URL, headers=await auth_headers(actor))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_audit_log_requires_authentication(client):
    assert (await client.get(URL)).status_code == 401


@pytest.mark.asyncio
async def test_filters_narrow_the_results_and_combine(client, make_user, auth_headers):
    admin = await make_user(role=UserRole.ADMIN)
    a, b = await make_user(), await make_user()
    headers = await auth_headers(admin)
    await _change_role(client, headers, a)
    await _change_role(client, headers, b)
    await client.patch(
        f"/api/v1/users/{a.id}/status", headers=headers, json={"is_active": False}
    )

    async def get(**params):
        return (await client.get(URL, headers=headers, params=params)).json()

    assert (await get(action="user.role_changed"))["total"] == 2
    assert (await get(resource_id=str(a.id)))["total"] == 2
    assert (await get(resource_id=str(a.id), action="user.deactivated"))["total"] == 1
    assert (await get(actor_user_id=str(admin.id)))["total"] == 3
    assert (await get(resource_type="user"))["total"] == 3
    assert (await get(resource_type="nothing"))["total"] == 0


@pytest.mark.asyncio
async def test_pagination_reports_the_full_total(client, make_user, auth_headers):
    admin = await make_user(role=UserRole.ADMIN)
    headers = await auth_headers(admin)
    for _ in range(5):
        await _change_role(client, headers, await make_user())

    page = (
        await client.get(URL, headers=headers, params={"limit": 2, "skip": 2})
    ).json()
    assert page["total"] == 5
    assert len(page["items"]) == 2

    ids = []
    for skip in (0, 2, 4):
        body = (
            await client.get(URL, headers=headers, params={"limit": 2, "skip": skip})
        ).json()
        ids += [e["id"] for e in body["items"]]
    assert len(ids) == len(set(ids)) == 5  # no overlap, nothing skipped


@pytest.mark.asyncio
async def test_page_size_is_capped(client, make_user, auth_headers):
    headers = await auth_headers(await make_user(role=UserRole.ADMIN))
    assert (
        await client.get(URL, headers=headers, params={"limit": 101})
    ).status_code == 422
    assert (
        await client.get(URL, headers=headers, params={"skip": -1})
    ).status_code == 422


@pytest.mark.asyncio
async def test_entries_survive_deleting_the_actor_but_lose_their_email(
    client, db_session, make_user, auth_headers
):
    reader = await make_user(role=UserRole.ADMIN)
    gone = await make_user(role=UserRole.ADMIN)
    await record_audit_event(
        db_session, action="x.did", resource_type="x", actor_user_id=gone.id
    )
    await db_session.delete(gone)
    await db_session.flush()

    body = (await client.get(URL, headers=await auth_headers(reader))).json()
    entry = next(e for e in body["items"] if e["action"] == "x.did")
    assert entry["actor_user_id"] == str(gone.id)
    assert entry["actor_email"] is None


@pytest.mark.asyncio
async def test_system_actions_with_no_actor_are_listed_too(
    client, db_session, make_user, auth_headers
):
    reader = await make_user(role=UserRole.ADMIN)
    await record_audit_event(db_session, action="job.ran", resource_type="job")

    body = (await client.get(URL, headers=await auth_headers(reader))).json()
    entry = next(e for e in body["items"] if e["action"] == "job.ran")
    assert entry["actor_user_id"] is None
    assert entry["actor_email"] is None


# --- where the action came from -----------------------------------------------


@pytest.mark.asyncio
async def test_the_callers_ip_and_user_agent_are_recorded_automatically(
    client, make_user, auth_headers
):
    admin = await make_user(role=UserRole.ADMIN)
    headers = await auth_headers(admin)
    await _change_role(
        client, headers, await make_user(), **{"User-Agent": "pytest-agent/1.0"}
    )

    entry = (await client.get(URL, headers=headers)).json()["items"][0]
    assert entry["ip_address"] == "127.0.0.1"
    assert entry["user_agent"] == "pytest-agent/1.0"


@pytest.mark.asyncio
async def test_an_oversized_user_agent_is_truncated_not_a_500(
    client, make_user, auth_headers
):
    admin = await make_user(role=UserRole.ADMIN)
    headers = await auth_headers(admin)
    response = await _change_role(
        client, headers, await make_user(), **{"User-Agent": "x" * 5000}
    )
    assert response.status_code == 200

    entry = (await client.get(URL, headers=headers)).json()["items"][0]
    assert len(entry["user_agent"]) == 512


@pytest.mark.asyncio
async def test_outside_a_request_no_ip_is_recorded(db_session):
    entry = await record_audit_event(db_session, action="job.ran", resource_type="job")
    assert entry.ip_address is None
    assert entry.user_agent is None
