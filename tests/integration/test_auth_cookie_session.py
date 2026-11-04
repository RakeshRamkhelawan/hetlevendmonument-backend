"""
Integration tests for the backend cookie session contract.

Covers:
- Login sets secure HttpOnly cookies
- Cookie-only auth works for current-user
- Refresh rotates the access_token cookie
- Revoke/logout clears cookies
- CSRF validation on mutating endpoints when cookie auth is active
"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class _FakeRedis:
    """Minimal in-memory Redis stand-in for CSRF tests."""

    def __init__(self):
        self._store = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def setex(self, key: str, seconds: int, value: str):
        self._store[key] = value

    async def ping(self):
        return True


@pytest.fixture(scope="function")
def fake_redis():
    return _FakeRedis()


_ADMIN_EMAIL = "admin@integration.test"
_ADMIN_PASS = "AdminPass123!"


async def _login_as_admin(client: AsyncClient) -> str:
    """Helper: log in as pre-seeded admin to establish a cookie session; geeft het token terug."""
    login_resp = await client.post(
        "/api/v1/auth/token",
        data={
            "username": _ADMIN_EMAIL,
            "password": _ADMIN_PASS,
            "grant_type": "password",
        },
    )
    assert login_resp.status_code == 200
    return str(login_resp.json()["access_token"])


async def _get_csrf_token(client: AsyncClient, fake_redis: _FakeRedis) -> str:
    """Helper: fetch a CSRF token for state-changing requests."""
    with patch("src.core.api.auth.router_csrf.get_redis_client", return_value=fake_redis):
        resp = await client.get("/api/v1/auth/csrf-token")
    assert resp.status_code == 200
    return resp.json()["csrf_token"]


@pytest.mark.asyncio
async def test_login_sets_http_only_cookie(
    integration_client: AsyncClient,
    db_session: AsyncSession,
):
    """Happy path: login sets access_token cookie and returns token body."""
    await _login_as_admin(integration_client)

    # Re-login to inspect Set-Cookie header
    login_resp = await integration_client.post(
        "/api/v1/auth/token",
        data={
            "username": _ADMIN_EMAIL,
            "password": _ADMIN_PASS,
            "grant_type": "password",
        },
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data

    set_cookie = login_resp.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie
    assert "HttpOnly" in set_cookie


@pytest.mark.asyncio
async def test_current_user_via_cookie_auth(
    integration_client: AsyncClient,
    db_session: AsyncSession,
):
    """Happy path: /me succeeds using only the cookie (no Authorization header)."""
    await _login_as_admin(integration_client)

    # Access /me WITHOUT Authorization header
    me_resp = await integration_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == _ADMIN_EMAIL


@pytest.mark.asyncio
async def test_refresh_rotates_access_cookie(
    integration_client: AsyncClient,
    db_session: AsyncSession,
):
    """Happy path: refresh endpoint sets a new access_token cookie."""
    await _login_as_admin(integration_client)

    # Capture current cookie value
    login_resp = await integration_client.post(
        "/api/v1/auth/token",
        data={
            "username": _ADMIN_EMAIL,
            "password": _ADMIN_PASS,
            "grant_type": "password",
        },
    )
    old_cookie = login_resp.headers.get("set-cookie", "")
    old_token = (
        old_cookie.split("access_token=")[1].split(";")[0] if "access_token=" in old_cookie else ""
    )
    refresh_token = login_resp.json()["refresh_token"]

    refresh_resp = await integration_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 200

    new_cookie = refresh_resp.headers.get("set-cookie", "")
    assert "access_token=" in new_cookie
    new_token = (
        new_cookie.split("access_token=")[1].split(";")[0] if "access_token=" in new_cookie else ""
    )
    assert new_token != old_token


@pytest.mark.asyncio
async def test_logout_clears_cookies(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: _FakeRedis,
):
    """Happy path: logout deletes access_token cookie."""
    await _login_as_admin(integration_client)

    csrf = await _get_csrf_token(integration_client, fake_redis)
    # Uitloggen schrijft het token naar de blacklist in de database (`oauth2_service.revoke_token`),
    # niet meer naar Redis: alleen de CSRF-controle in `dependencies` gebruikt nog Redis.
    with patch("src.core.api.auth.dependencies.get_redis_client", return_value=fake_redis):
        logout_resp = await integration_client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf},
        )
    assert logout_resp.status_code == 200

    set_cookie = logout_resp.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie or "access_token" in set_cookie


@pytest.mark.asyncio
async def test_cookie_auth_fails_after_logout(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: _FakeRedis,
):
    """Unhappy path: after logout the cookie no longer authenticates, and neither does the token.

    Twee dingen, met opzet: (1) de client stuurt na het uitloggen geen cookie meer; (2) HETZELFDE
    token, opnieuw aangeboden, wordt geweigerd. Alleen (1) zegt niets over de blacklist: de client
    stuurt dan gewoon niets. Het bewijs op de echte voordeur staat in
    `tests/integration/security/test_een_uitgelogd_token_wordt_geweigerd.py`.
    """
    token = await _login_as_admin(integration_client)

    csrf = await _get_csrf_token(integration_client, fake_redis)
    with patch("src.core.api.auth.dependencies.get_redis_client", return_value=fake_redis):
        logout_resp = await integration_client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf},
        )
    assert logout_resp.status_code == 200

    me_resp = await integration_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 401

    replay_resp = await integration_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert replay_resp.status_code == 401


@pytest.mark.asyncio
async def test_csrf_required_for_state_changing_request(
    integration_client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: _FakeRedis,
):
    """
    Unhappy path: a state-changing request that uses cookie auth
    but omits the X-CSRF-Token header must be rejected.
    """
    await _login_as_admin(integration_client)

    # Logout without CSRF header must be rejected
    with patch("src.core.api.auth.dependencies.get_redis_client", return_value=fake_redis):
        logout_resp = await integration_client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 403

    # Logout WITH CSRF header must succeed
    csrf = await _get_csrf_token(integration_client, fake_redis)
    with patch("src.core.api.auth.dependencies.get_redis_client", return_value=fake_redis):
        logout_ok = await integration_client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf},
        )
    assert logout_ok.status_code == 200
