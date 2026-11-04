"""Wekelijkse archiefexport over alle tenants (BE-EP-054, Gate 2 H1/M7).

Een mislukte tenant mag de andere niet tegenhouden, en een mislukking mag niet stil zijn.
De twee hulpfuncties zijn gepatcht; de lus en de telling zijn echt.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from src.core.services.foundation_archive_service import ArchiveExportError
from src.workers import actors

_NU = datetime(2026, 11, 8, 2, 15, tzinfo=timezone.utc)
_TENANTS = [(1, "een", "Een"), (2, "twee", "Twee")]


@pytest.mark.asyncio
async def test_na_een_mislukte_tenant_wordt_de_volgende_toch_geexporteerd() -> None:
    per_tenant = AsyncMock(side_effect=[ArchiveExportError("bestand weg"), None])

    with (
        patch.object(actors, "_foundation_portaal_tenants", AsyncMock(return_value=_TENANTS)),
        patch.object(actors, "_exporteer_archief_voor_tenant", per_tenant),
    ):
        with pytest.raises(RuntimeError):
            await actors._run_foundation_archive_exports(now=_NU)

    assert [c.args[0] for c in per_tenant.await_args_list] == [1, 2]


@pytest.mark.asyncio
async def test_een_databasefout_bij_een_tenant_houdt_de_rest_niet_tegen() -> None:
    per_tenant = AsyncMock(side_effect=[OperationalError("x", {}, Exception("db")), None])

    with (
        patch.object(actors, "_foundation_portaal_tenants", AsyncMock(return_value=_TENANTS)),
        patch.object(actors, "_exporteer_archief_voor_tenant", per_tenant),
    ):
        with pytest.raises(RuntimeError):
            await actors._run_foundation_archive_exports(now=_NU)

    assert per_tenant.await_count == 2


@pytest.mark.asyncio
async def test_een_mislukking_is_niet_stil() -> None:
    with (
        patch.object(actors, "_foundation_portaal_tenants", AsyncMock(return_value=_TENANTS)),
        patch.object(
            actors, "_exporteer_archief_voor_tenant", AsyncMock(side_effect=[None, ArchiveExportError("x")])
        ),
    ):
        with pytest.raises(RuntimeError, match="1 van 2"):
            await actors._run_foundation_archive_exports(now=_NU)


@pytest.mark.asyncio
async def test_zonder_fouten_telt_de_taak_elke_tenant() -> None:
    with (
        patch.object(actors, "_foundation_portaal_tenants", AsyncMock(return_value=_TENANTS)),
        patch.object(actors, "_exporteer_archief_voor_tenant", AsyncMock(return_value=None)),
    ):
        uitslag = await actors._run_foundation_archive_exports(now=_NU)

    assert uitslag == {"exported": 2, "failed": 0}


@pytest.mark.asyncio
async def test_een_mislukte_commit_in_de_taak_verwijdert_het_pakket() -> None:
    from contextlib import asynccontextmanager
    from unittest.mock import MagicMock

    sessie = AsyncMock()
    sessie.commit.side_effect = OperationalError("commit", {}, Exception("db weg"))

    @asynccontextmanager
    async def _sessie():  # type: ignore[no-untyped-def]
        yield sessie

    export = MagicMock()
    dienst = MagicMock()
    dienst.export = AsyncMock(return_value=export)
    dienst.discard = AsyncMock()

    with (
        patch("src.core.database.session.get_db_session", _sessie),
        patch(
            "src.core.services.foundation_archive_service.FoundationArchiveService",
            return_value=dienst,
        ),
    ):
        with pytest.raises(OperationalError):
            await actors._exporteer_archief_voor_tenant(1, "een", "Een", _NU)

    dienst.discard.assert_awaited_once_with(export)
