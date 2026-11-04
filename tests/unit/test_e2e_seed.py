"""Unit tests for Fase 10 E2E seed helpers."""

import pytest

from src.core.company.e2e_seed import SeedError, SeedStore, seed_company_layer


def test_seed_creates_tenant() -> None:
    store = SeedStore()
    result = seed_company_layer(store, tenant_slug="tenant-one")

    assert result["tenant"]["slug"] == "tenant-one"
    assert "tenant-one" in store.tenants


def test_seed_creates_users_with_roles() -> None:
    store = SeedStore()
    result = seed_company_layer(store, tenant_slug="tenant-two")

    roles = {user["role"] for user in result["users"]}
    assert roles == {"admin", "cfo", "cto"}


def test_seed_creates_company_with_departments() -> None:
    store = SeedStore()
    result = seed_company_layer(store, tenant_slug="tenant-three")

    assert result["company"]["name"] == "E2E Company"
    assert len(result["departments"]) == 3


def test_seed_idempotent() -> None:
    store = SeedStore()
    first = seed_company_layer(store, tenant_slug="tenant-four")
    second = seed_company_layer(store, tenant_slug="tenant-four")

    assert first["company"]["id"] == second["company"]["id"]
    assert len(store.users) == 3
    assert len(store.departments) == 3


def test_seed_fails_without_db() -> None:
    store = SeedStore(connected=False)

    with pytest.raises(SeedError, match="Database connection"):
        seed_company_layer(store, tenant_slug="tenant-five")


def test_seed_partial_rollback() -> None:
    store = SeedStore()

    with pytest.raises(SeedError, match="Forced failure"):
        seed_company_layer(store, tenant_slug="tenant-six", fail_step="departments")

    assert store.tenants == {}
    assert store.users == {}
    assert store.companies == {}
    assert store.departments == {}
