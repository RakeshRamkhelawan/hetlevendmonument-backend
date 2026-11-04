"""De publieke tenant-scopes geven de tenant door aan de al lopende transactie (ADR-036 OP-151).

Gemeten 2026-11-02 op productie (applicatierol `sanskritisetu_app`): de tenant werd gevonden,
maar `/content` gaf total=0 terwijl vijf goedgekeurde PUBLIC-items in de tabel stonden. De
opzoekquery opent de transactie met een lege `app.current_tenant`; `set_tenant_id` daarna
veranderde alleen de ContextVar.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.services import foundation_tenant_resolver as resolver

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _sessie(dialect: str = "postgresql", in_transactie: bool = True) -> Any:
    sessie = MagicMock()
    sessie.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
    sessie.in_transaction = MagicMock(return_value=in_transactie)
    sessie.execute = AsyncMock()
    return sessie


def _set_config_waarden(sessie: Any) -> list[str]:
    waarden = []
    for aanroep in sessie.execute.await_args_list:
        sql = str(aanroep.args[0])
        if "set_config('app.current_tenant'" in sql:
            waarden.append(aanroep.args[1]["t"])
    return waarden


async def test_scope_op_slug_zet_de_tenant_in_de_lopende_transactie() -> None:
    sessie = _sessie()
    with patch.object(resolver, "resolve_tenant_by_slug", AsyncMock(return_value=SimpleNamespace(id=3))):
        async with resolver.public_tenant_scope("hetlevendmonument", sessie) as tenant:
            assert tenant.id == 3
            assert _set_config_waarden(sessie) == ["3"]


async def test_scope_op_host_zet_de_tenant_in_de_lopende_transactie() -> None:
    sessie = _sessie()
    with patch.object(resolver, "resolve_tenant_by_host", AsyncMock(return_value=SimpleNamespace(id=7))):
        async with resolver.public_tenant_scope_by_host("hetlevendmonument.nl", sessie):
            assert _set_config_waarden(sessie) == ["7"]


async def test_geen_set_config_buiten_postgresql() -> None:
    sessie = _sessie(dialect="sqlite")
    with patch.object(resolver, "resolve_tenant_by_slug", AsyncMock(return_value=SimpleNamespace(id=3))):
        async with resolver.public_tenant_scope("hetlevendmonument", sessie):
            assert _set_config_waarden(sessie) == []


async def test_geen_set_config_zonder_lopende_transactie() -> None:
    """Zonder transactie zet het begin-event van de volgende transactie de waarde zelf."""
    sessie = _sessie(in_transactie=False)
    with patch.object(resolver, "resolve_tenant_by_slug", AsyncMock(return_value=SimpleNamespace(id=3))):
        async with resolver.public_tenant_scope("hetlevendmonument", sessie):
            assert _set_config_waarden(sessie) == []
