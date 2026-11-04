"""
E2E Test Configuration
======================

Centralized configuration for E2E tests that hit the live backend.

The base URL defaults to http://localhost:8110 (matching docker-compose.dev.yml).
Override via TEST_BASE_URL environment variable.
"""

import asyncio
import os
from datetime import datetime, timezone

import httpx
import pytest

def _discover_e2e_base_url() -> str:
    env_url = os.getenv("TEST_BASE_URL")
    if env_url:
        return env_url
    import urllib.request
    candidates = ["http://127.0.0.1:8001", "http://localhost:8110"]
    for candidate in candidates:
        try:
            with urllib.request.urlopen(f"{candidate}/health", timeout=2) as resp:
                data = resp.read().decode("utf-8")
                if '"status"' in data or "status" in data:
                    return candidate
        except Exception:
            continue
    return "http://localhost:8110"


E2E_BASE_URL = _discover_e2e_base_url()


@pytest.fixture
def e2e_base_url() -> str:
    """Base URL for the running backend server."""
    return E2E_BASE_URL


async def e2e_register_user(
    client: httpx.AsyncClient,
    email: str,
    password: str,
    max_retries: int = 5,
) -> httpx.Response:
    """Register a user with retry logic for rate limiting (429)."""
    for attempt in range(max_retries):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        if response.status_code != 429:
            return response
        wait = int(response.headers.get("Retry-After", 15))
        await asyncio.sleep(wait)
    return response


async def e2e_login_user(
    client: httpx.AsyncClient,
    email: str,
    password: str,
    max_retries: int = 5,
) -> httpx.Response:
    """Login a user with retry logic for rate limiting (429)."""
    for attempt in range(max_retries):
        response = await client.post(
            "/api/v1/auth/token",
            data={"username": email, "password": password},
        )
        if response.status_code != 429:
            return response
        wait = int(response.headers.get("Retry-After", 15))
        await asyncio.sleep(wait)
    return response


async def e2e_register_and_login(
    client: httpx.AsyncClient,
    email: str | None = None,
    password: str = "TestPassword123!",
) -> tuple[str | None, str]:
    """Register a user and return (access_token, email). Token is None on failure."""
    if email is None:
        ts = datetime.now(timezone.utc).isoformat().replace(":", "-").replace(".", "-")
        email = f"e2e_{ts}@example.com"

    await e2e_register_user(client, email, password)
    login_resp = await e2e_login_user(client, email, password)

    if login_resp.status_code == 200:
        data = login_resp.json()
        return data.get("access_token"), email
    return None, email


def e2e_register_user_sync(
    client: httpx.Client,
    email: str,
    password: str,
    max_retries: int = 5,
) -> httpx.Response:
    """Sync version: register a user with retry logic for rate limiting."""
    import time

    for attempt in range(max_retries):
        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        if response.status_code != 429:
            return response
        wait = int(response.headers.get("Retry-After", 15))
        time.sleep(wait)
    return response


def e2e_login_user_sync(
    client: httpx.Client,
    email: str,
    password: str,
    max_retries: int = 5,
) -> httpx.Response:
    """Sync version: login a user with retry logic for rate limiting."""
    import time

    for attempt in range(max_retries):
        response = client.post(
            "/api/v1/auth/token",
            data={"username": email, "password": password},
        )
        if response.status_code != 429:
            return response
        wait = int(response.headers.get("Retry-After", 15))
        time.sleep(wait)
    return response
