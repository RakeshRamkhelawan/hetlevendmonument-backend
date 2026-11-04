"""require_edu_session geeft de tenant door aan de lopende transactie VOOR de toegangsquery.

Gemeten 2026-11-02 bij de rooktest van productie (applicatierol, RLS actief): de opzoekquery
van de tenant opende de transactie met een lege `app.current_tenant`, waarna de query op
`educational_access` nul rijen gaf. Elke edu-sessie was daardoor ongeldig (401).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.api.v1.foundation import dependencies as deps

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _sessie(volgorde: list[str]) -> Any:
    sessie = MagicMock()
    sessie.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    sessie.in_transaction = MagicMock(return_value=True)
    toegang = SimpleNamespace(is_active=True, expires_at=None, tenant_id=3, id=1)

    async def execute(stmt: Any, params: Any = None) -> Any:
        sql = str(stmt)
        if "set_config('app.current_tenant'" in sql:
            volgorde.append(f"set_config:{params['t']}")
            return MagicMock()
        volgorde.append("select_toegang")
        resultaat = MagicMock()
        resultaat.scalar_one_or_none = MagicMock(return_value=toegang)
        return resultaat

    sessie.execute = AsyncMock(side_effect=execute)
    return sessie


async def test_tenant_staat_in_de_transactie_voor_de_toegangsquery() -> None:
    volgorde: list[str] = []
    verzoek = SimpleNamespace(cookies={deps.SESSION_COOKIE_NAME: "sessie-1"})
    store = MagicMock()
    store.get_session = AsyncMock(return_value=SimpleNamespace(access_id=1, tenant_id=3))
    with patch.object(deps, "resolve_tenant_by_slug", AsyncMock(return_value=SimpleNamespace(id=3))):
        ctx = await deps.require_edu_session(
            verzoek, "hetlevendmonument", session=_sessie(volgorde), edu_sessions=store
        )
    assert ctx.tenant.id == 3
    assert volgorde == ["set_config:3", "select_toegang"]
