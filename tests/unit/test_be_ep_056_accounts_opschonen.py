"""BE-EP-056: ongebruikte vertelleraccounts worden opgeruimd, en verder niets.

Regels die deze tests bewaken (zie src/core/services/foundation_accounts.py):
1. Alleen rol visitor, niet geverifieerd, nooit ingelogd, ouder dan 7 dagen.
2. Nooit een account waar een verhaal, klas, archiefexport of docentaanvraag naar wijst.
3. Met tenant_id alleen die tenant.
4. De nachtelijke job roept het opruimen echt aan.
"""

from __future__ import annotations

import contextlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from src.core.models.foundation_content import (
    FoundationArchiveExport,
    FoundationContent,
    FoundationTeacherApplication,
    PortalUser,
    StudyCollection,
)
from src.core.services import foundation_accounts, foundation_leerlingantwoorden
from src.core.services.foundation_accounts import (
    ONGEBRUIKT_NA,
    ongebruikte_accounts_stmt,
    verwijder_ongebruikte_accounts,
)

NU = datetime(2026, 11, 20, 2, 30, tzinfo=timezone.utc)
PU = PortalUser.__tablename__


def _sql(tenant_id: int | None = None) -> tuple[str, dict[str, Any]]:
    gecompileerd = ongebruikte_accounts_stmt(NU, tenant_id).compile(dialect=postgresql.dialect())
    return " ".join(str(gecompileerd).split()), dict(gecompileerd.params)


def _waarde(params: dict[str, Any], sql: str, kolom: str) -> Any:
    treffer = re.search(rf"{PU}\.{kolom} (?:=|<) %\((\w+)\)s", sql)
    assert treffer, f"geen voorwaarde op {kolom}"
    return params[treffer.group(1)]


def test_het_gaat_om_een_delete_op_de_accounttabel() -> None:
    sql, _ = _sql()
    assert sql.startswith(f"DELETE FROM {PU} WHERE ")


def test_alleen_bezoekers() -> None:
    sql, params = _sql()
    rol = _waarde(params, sql, "role")
    assert getattr(rol, "value", rol) == "visitor"


def test_alleen_als_de_link_nooit_is_gebruikt() -> None:
    sql, _ = _sql()
    assert f"{PU}.is_verified IS false" in sql
    assert f"{PU}.email_verified IS false" in sql
    assert f"{PU}.last_login_at IS NULL" in sql


def test_pas_na_zeven_dagen() -> None:
    sql, params = _sql()
    assert ONGEBRUIKT_NA == timedelta(days=7)
    assert _waarde(params, sql, "created_at") == NU - timedelta(days=7)


@pytest.mark.parametrize(
    ("tabel", "kolom"),
    [
        (FoundationContent.__tablename__, "uploader_id"),
        (StudyCollection.__tablename__, "owner_portal_user_id"),
        (FoundationArchiveExport.__tablename__, "created_by_portal_user_id"),
        (FoundationTeacherApplication.__tablename__, "portal_user_id"),
        (FoundationTeacherApplication.__tablename__, "decided_by_portal_user_id"),
    ],
)
def test_nooit_een_account_waar_iets_naar_wijst(tabel: str, kolom: str) -> None:
    sql, _ = _sql()
    verwacht = f"NOT (EXISTS (SELECT * FROM {tabel} WHERE {tabel}.{kolom} = {PU}.id))"
    assert verwacht in sql


def test_de_subquery_hangt_aan_het_account_zelf() -> None:
    # Een niet-gecorreleerde subquery (FROM tabel, portal_users) zou ALLE accounts
    # tegelijk beoordelen; de FROM in elke subquery mag dus alleen de eigen tabel noemen.
    sql, _ = _sql()
    for van in re.findall(r"SELECT \* FROM ([\w, ]+?) WHERE", sql):
        assert PU not in van


def test_met_tenant_alleen_die_tenant() -> None:
    zonder, _ = _sql()
    met, params = _sql(tenant_id=3)
    assert f"{PU}.tenant_id" not in zonder
    assert _waarde(params, met, "tenant_id") == 3


@pytest.mark.asyncio
async def test_geeft_het_aantal_verwijderde_accounts() -> None:
    sessie = AsyncMock()
    resultaat = MagicMock()
    resultaat.rowcount = 4
    sessie.execute.return_value = resultaat
    assert await verwijder_ongebruikte_accounts(sessie, NU) == 4


@pytest.mark.asyncio
async def test_de_nachtelijke_job_ruimt_ook_accounts_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x/y")
    engine = MagicMock()
    engine.dispose = AsyncMock()
    sessie = AsyncMock()
    tenants = MagicMock()
    tenants.scalars.return_value.all.return_value = [7]
    sessie.execute.return_value = tenants

    @contextlib.asynccontextmanager
    async def maak_sessie(_engine: Any):  # noqa: ARG001
        yield sessie

    accounts = AsyncMock(return_value=2)
    with patch.object(foundation_leerlingantwoorden, "create_async_engine", return_value=engine), patch.object(
        foundation_leerlingantwoorden, "AsyncSession", side_effect=maak_sessie
    ), patch.object(foundation_leerlingantwoorden, "verwijder_verlopen_antwoorden", new=AsyncMock(return_value=0)), patch.object(
        foundation_accounts, "verwijder_ongebruikte_accounts", new=accounts
    ):
        await foundation_leerlingantwoorden._main()

    accounts.assert_awaited_once()
    assert accounts.await_args.args[2] == 7
    sessie.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_de_job_zet_per_tenant_de_tenantcontext(monkeypatch: pytest.MonkeyPatch) -> None:
    """FORCE RLS geldt ook voor de eigenaar: zonder context verwijdert de job stil niets."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x/y")
    engine = MagicMock()
    engine.dispose = AsyncMock()
    sessie = AsyncMock()
    tenants = MagicMock()
    tenants.scalars.return_value.all.return_value = [3, 7]
    sessie.execute.return_value = tenants

    @contextlib.asynccontextmanager
    async def maak_sessie(_engine: Any):  # noqa: ARG001
        yield sessie

    antwoorden = AsyncMock(return_value=1)
    accounts = AsyncMock(return_value=2)
    with patch.object(foundation_leerlingantwoorden, "create_async_engine", return_value=engine), patch.object(
        foundation_leerlingantwoorden, "AsyncSession", side_effect=maak_sessie
    ), patch.object(foundation_leerlingantwoorden, "verwijder_verlopen_antwoorden", new=antwoorden), patch.object(
        foundation_accounts, "verwijder_ongebruikte_accounts", new=accounts
    ):
        await foundation_leerlingantwoorden._main()

    contexten = [
        c.args[1]["tenant"]
        for c in sessie.execute.await_args_list
        if "set_config('app.current_tenant'" in str(c.args[0])
    ]
    assert contexten == ["3", "7"]
    assert [c.args[2] for c in antwoorden.await_args_list] == [3, 7]
    assert [c.args[2] for c in accounts.await_args_list] == [3, 7]
    assert sessie.commit.await_count == 2
