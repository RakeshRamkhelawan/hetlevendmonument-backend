"""Utility helpers used by Fase 10 E2E seed tests.

These helpers keep the seed logic deterministic and idempotent so unit tests
can validate behavior without requiring a live database.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SeedStore:
    """Minimal in-memory store for E2E seed operations."""

    connected: bool = True
    tenants: dict[str, dict[str, Any]] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    users: dict[str, dict[str, Any]] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    companies: dict[str, dict[str, Any]] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    departments: dict[str, dict[str, Any]] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class SeedError(RuntimeError):
    """Raised when seeding cannot continue safely."""


def _upsert_tenant(store: SeedStore, slug: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    return store.tenants.setdefault(
        slug,
        {
            "id": f"tenant-{slug}",
            "slug": slug,
            "name": slug.replace("-", " ").title(),
        },
    )


def _upsert_user(store: SeedStore, tenant_id: str, email: str, role: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    return store.users.setdefault(
        email,
        {
            "id": f"user-{email.split('@')[0]}",
            "tenant_id": tenant_id,
            "email": email,
            "role": role,
        },
    )


def _upsert_company(store: SeedStore, tenant_id: str, name: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    key = f"{tenant_id}:{name.lower()}"
    return store.companies.setdefault(
        key,
        {
            "id": f"company-{name.lower().replace(' ', '-')}",
            "tenant_id": tenant_id,
            "name": name,
        },
    )


def _upsert_department(store: SeedStore, company_id: str, name: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    key = f"{company_id}:{name.lower()}"
    return store.departments.setdefault(
        key,
        {
            "id": f"dept-{name.lower().replace(' ', '-')}",
            "company_id": company_id,
            "name": name,
        },
    )


def seed_company_layer(
    store: SeedStore, *, tenant_slug: str, fail_step: str | None = None
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Seed core company E2E entities with transaction-like rollback."""
    if not store.connected:
        raise SeedError("Database connection is not available")

    snapshot = deepcopy(store)

    try:
        tenant = _upsert_tenant(store, tenant_slug)
        if fail_step == "tenant":
            raise SeedError("Forced failure during tenant seed")

        users = [
            _upsert_user(store, tenant["id"], f"admin@{tenant_slug}.test", "admin"),
            _upsert_user(store, tenant["id"], f"cfo@{tenant_slug}.test", "cfo"),
            _upsert_user(store, tenant["id"], f"cto@{tenant_slug}.test", "cto"),
        ]
        if fail_step == "users":
            raise SeedError("Forced failure during user seed")

        company = _upsert_company(store, tenant["id"], "E2E Company")
        if fail_step == "company":
            raise SeedError("Forced failure during company seed")

        departments = [
            _upsert_department(store, company["id"], "Finance"),
            _upsert_department(store, company["id"], "Technology"),
            _upsert_department(store, company["id"], "Operations"),
        ]
        if fail_step == "departments":
            raise SeedError("Forced failure during department seed")

        return {
            "tenant": tenant,
            "users": users,
            "company": company,
            "departments": departments,
        }
    except Exception:
        store.tenants = snapshot.tenants
        store.users = snapshot.users
        store.companies = snapshot.companies
        store.departments = snapshot.departments
        raise
