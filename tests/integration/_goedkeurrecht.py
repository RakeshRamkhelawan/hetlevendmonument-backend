"""Gedeelde fixture: gebruikers 1 en 101 van tenant 1 krijgen de rol `goedkeurder` (ADR-039).

Goedkeuren is sinds 2026-10-09 een procesbevoegdheid, geen beheerdersrecht: de HITL-routes toetsen
`receivables:approve` in `role_permissions`. Integratietests die een ticket door de ECHTE route
goedkeuren of afwijzen, hebben dus een gebruiker met dat recht nodig. Deze fixture voegt de rol toe
aan de bestaande rollen van beide gebruikers en zet de oorspronkelijke toestand na afloop terug.

Gebruik: `from tests.integration._goedkeurrecht import goedkeurder_gebruikers  # noqa: F401`
en dan `@pytest.mark.usefixtures("goedkeurder_gebruikers")` of als parameter.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from sqlalchemy import text

TENANT = 1
GEBRUIKERS = (1, 101)


async def _sql(query: str, **params: Any) -> Any:
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        result = await session.execute(text(query), params)
        await session.commit()
        return result


@pytest_asyncio.fixture
async def goedkeurder_gebruikers() -> AsyncGenerator[None, None]:
    from src.core.database.bypass_session import adopt_tenant
    from src.core.database.database import db_manager
    from src.core.services.rbac_service import RBACService

    async with db_manager.get_session() as session:
        async with adopt_tenant(session, TENANT):
            await RBACService(session).ensure_default_roles(TENANT)
        await session.commit()
    oud = list(
        (
            await _sql(
                "SELECT user_id, role_id FROM user_roles WHERE tenant_id = :t "
                "AND user_id IN (:a, :b)",
                t=TENANT,
                a=GEBRUIKERS[0],
                b=GEBRUIKERS[1],
            )
        ).all()
    )
    for user_id in GEBRUIKERS:
        await _sql(
            "INSERT INTO user_roles (user_id, role_id, tenant_id) "
            "SELECT :u, id, :t FROM roles WHERE tenant_id = :t AND name = 'goedkeurder' "
            "AND NOT EXISTS (SELECT 1 FROM user_roles x WHERE x.user_id = :u "
            "AND x.role_id = roles.id)",
            u=user_id,
            t=TENANT,
        )
    yield
    await _sql(
        "DELETE FROM user_roles WHERE tenant_id = :t AND user_id IN (:a, :b)",
        t=TENANT,
        a=GEBRUIKERS[0],
        b=GEBRUIKERS[1],
    )
    for user_id, role_id in oud:
        await _sql(
            "INSERT INTO user_roles (user_id, role_id, tenant_id) VALUES (:u, :r, :t)",
            u=user_id,
            r=role_id,
            t=TENANT,
        )
