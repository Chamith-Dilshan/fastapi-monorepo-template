"""Who can do what to whom — the RBAC rules in app/api/v1/users.py and
UserService, exercised through the real HTTP API."""

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.user import UserRole

USERS = "/api/v1/users"


# --- reading --------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_request_is_401(client):
    response = await client.get(USERS)
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (UserRole.ADMIN, 200),
        (UserRole.MANAGER, 200),
        (UserRole.USER, 403),
        (UserRole.GUEST, 403),
    ],
)
async def test_listing_users_by_role(client, make_user, auth_headers, role, expected):
    actor = await make_user(role=role)
    response = await client.get(USERS, headers=await auth_headers(actor))
    assert response.status_code == expected
    if expected == 403:
        assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.asyncio
async def test_user_can_read_self_but_not_others(client, make_user, auth_headers):
    me = await make_user()
    other = await make_user()
    headers = await auth_headers(me)

    assert (await client.get(f"{USERS}/{me.id}", headers=headers)).status_code == 200
    assert (await client.get(f"{USERS}/{other.id}", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_manager_can_read_other_users(client, make_user, auth_headers):
    manager = await make_user(role=UserRole.MANAGER)
    other = await make_user()
    response = await client.get(
        f"{USERS}/{other.id}", headers=await auth_headers(manager)
    )
    assert response.status_code == 200


# --- editing --------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_can_edit_own_profile(client, make_user, auth_headers):
    me = await make_user()
    response = await client.patch(
        f"{USERS}/{me.id}",
        headers=await auth_headers(me),
        json={"first_name": "Renamed"},
    )
    assert response.status_code == 200
    assert response.json()["first_name"] == "Renamed"


@pytest.mark.asyncio
async def test_user_cannot_edit_someone_else(client, make_user, auth_headers):
    me = await make_user()
    other = await make_user()
    response = await client.patch(
        f"{USERS}/{other.id}",
        headers=await auth_headers(me),
        json={"first_name": "Hacked"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_edit_anyone(client, make_user, auth_headers):
    admin = await make_user(role=UserRole.ADMIN)
    other = await make_user()
    response = await client.patch(
        f"{USERS}/{other.id}",
        headers=await auth_headers(admin),
        json={"last_name": "ByAdmin"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_profile_update_cannot_smuggle_in_a_role_change(
    client, make_user, auth_headers
):
    me = await make_user()
    response = await client.patch(
        f"{USERS}/{me.id}",
        headers=await auth_headers(me),
        json={"first_name": "Sneaky", "role": "admin", "is_active": True},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "user"


@pytest.mark.asyncio
async def test_explicit_null_name_is_ignored_not_a_500(client, make_user, auth_headers):
    me = await make_user()
    response = await client.patch(
        f"{USERS}/{me.id}", headers=await auth_headers(me), json={"first_name": None}
    )
    assert response.status_code == 200
    assert response.json()["first_name"] == me.first_name


# --- role changes ---------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_changes_role_and_it_is_audited(
    client, db_session, make_user, auth_headers
):
    admin = await make_user(role=UserRole.ADMIN)
    target = await make_user()

    response = await client.patch(
        f"{USERS}/{target.id}/role",
        headers=await auth_headers(admin),
        json={"role": "manager"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "manager"

    entries = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.action == "user.role_changed")
            )
        )
        .scalars()
        .all()
    )
    assert len(entries) == 1
    assert entries[0].actor_user_id == admin.id
    assert entries[0].resource_id == str(target.id)
    assert entries[0].before == {"role": "user"}
    assert entries[0].after == {"role": "manager"}


@pytest.mark.asyncio
async def test_role_change_to_same_role_writes_no_audit_entry(
    client, db_session, make_user, auth_headers
):
    admin = await make_user(role=UserRole.ADMIN)
    target = await make_user()
    await client.patch(
        f"{USERS}/{target.id}/role",
        headers=await auth_headers(admin),
        json={"role": "user"},
    )
    count = len((await db_session.execute(select(AuditLog))).scalars().all())
    assert count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.USER, UserRole.GUEST])
async def test_only_admins_can_change_roles(client, make_user, auth_headers, role):
    actor = await make_user(role=role)
    target = await make_user()
    response = await client.patch(
        f"{USERS}/{target.id}/role",
        headers=await auth_headers(actor),
        json={"role": "admin"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_change_their_own_role(client, make_user, auth_headers):
    admin = await make_user(role=UserRole.ADMIN)
    response = await client.patch(
        f"{USERS}/{admin.id}/role",
        headers=await auth_headers(admin),
        json={"role": "user"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_promoted_user_gets_new_powers_on_the_same_token(
    client, make_user, auth_headers
):
    admin = await make_user(role=UserRole.ADMIN)
    target = await make_user()
    target_headers = await auth_headers(target)
    assert (await client.get(USERS, headers=target_headers)).status_code == 403

    await client.patch(
        f"{USERS}/{target.id}/role",
        headers=await auth_headers(admin),
        json={"role": "manager"},
    )
    # Same access token, no re-login: the role is read from the database
    # on every request, not frozen into the token.
    assert (await client.get(USERS, headers=target_headers)).status_code == 200


# --- activation -----------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivating_a_user_cuts_off_their_existing_token(
    client, make_user, auth_headers
):
    admin = await make_user(role=UserRole.ADMIN)
    target = await make_user()
    target_headers = await auth_headers(target)
    assert (
        await client.get("/api/v1/auth/me", headers=target_headers)
    ).status_code == 200

    response = await client.patch(
        f"{USERS}/{target.id}/status",
        headers=await auth_headers(admin),
        json={"is_active": False},
    )
    assert response.status_code == 200

    # Immediately, not when the token happens to expire.
    assert (
        await client.get("/api/v1/auth/me", headers=target_headers)
    ).status_code == 401
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": target.email, "password": "StrongP@ssw0rd!"},
    )
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_reactivating_restores_access_and_both_changes_are_audited(
    client, db_session, make_user, auth_headers
):
    admin = await make_user(role=UserRole.ADMIN)
    target = await make_user()
    admin_headers = await auth_headers(admin)

    for active in (False, True):
        r = await client.patch(
            f"{USERS}/{target.id}/status",
            headers=admin_headers,
            json={"is_active": active},
        )
        assert r.status_code == 200

    actions = [
        e.action
        for e in (
            await db_session.execute(select(AuditLog).order_by(AuditLog.created_at))
        )
        .scalars()
        .all()
    ]
    assert actions == ["user.deactivated", "user.activated"]


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_themselves(client, make_user, auth_headers):
    admin = await make_user(role=UserRole.ADMIN)
    response = await client.patch(
        f"{USERS}/{admin.id}/status",
        headers=await auth_headers(admin),
        json={"is_active": False},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_setting_the_status_a_user_already_has_is_a_noop(
    client, make_user, auth_headers
):
    admin = await make_user(role=UserRole.ADMIN)
    target = await make_user()
    response = await client.patch(
        f"{USERS}/{target.id}/status",
        headers=await auth_headers(admin),
        json={"is_active": True},
    )
    assert response.status_code == 200


# --- deleting -------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_deletes_a_user_and_it_is_audited(
    client, db_session, make_user, auth_headers
):
    admin = await make_user(role=UserRole.ADMIN)
    target = await make_user()
    headers = await auth_headers(admin)

    assert (
        await client.delete(f"{USERS}/{target.id}", headers=headers)
    ).status_code == 204
    assert (
        await client.get(f"{USERS}/{target.id}", headers=headers)
    ).status_code == 404

    entry = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "user.deleted")
        )
    ).scalar_one()
    assert entry.before == {"email": target.email, "role": "user"}


@pytest.mark.asyncio
async def test_non_admins_cannot_delete(client, make_user, auth_headers):
    manager = await make_user(role=UserRole.MANAGER)
    target = await make_user()
    response = await client.delete(
        f"{USERS}/{target.id}", headers=await auth_headers(manager)
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_delete_themselves(client, make_user, auth_headers):
    admin = await make_user(role=UserRole.ADMIN)
    response = await client.delete(
        f"{USERS}/{admin.id}", headers=await auth_headers(admin)
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_token_of_a_deleted_user_is_401_not_404(client, make_user, auth_headers):
    admin = await make_user(role=UserRole.ADMIN)
    target = await make_user()
    target_headers = await auth_headers(target)
    await client.delete(f"{USERS}/{target.id}", headers=await auth_headers(admin))

    response = await client.get("/api/v1/auth/me", headers=target_headers)
    assert response.status_code == 401
