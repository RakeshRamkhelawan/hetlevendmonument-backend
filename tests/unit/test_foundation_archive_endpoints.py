"""Beheerendpoints archiefexport (BE-EP-054): tenant-isolatie, rol, wachttijd, fouten.

Patroon van de andere foundation-unittests: de routefuncties direct aanroepen met een echte
tenant en gebruiker, de sessie gemockt. `public_tenant_scope` levert de tenant van de slug.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from src.core.api.v1.foundation.admin import archief
from src.core.api.v1.foundation.dependencies import require_curator
from src.core.models.foundation_content import FoundationArchiveExport, PortalRole, PortalUser
from src.core.models.rbac_models import Tenant

_NU = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def _tenant(tenant_id: int = 5) -> Tenant:
    return Tenant(id=tenant_id, slug="ketikoti", name="Stichting", is_active=True)


def _gebruiker(tenant_id: int, rol: PortalRole = PortalRole.CURATOR) -> PortalUser:
    return PortalUser(id=9, tenant_id=tenant_id, email="c@example.org", role=rol)


def _scope(tenant: Tenant) -> MagicMock:
    ctx = AsyncMock()
    ctx.__aenter__.return_value = tenant
    ctx.__aexit__.return_value = None
    return MagicMock(return_value=ctx)


def _uitslag(waarde: object) -> MagicMock:
    resultaat = MagicMock()
    resultaat.scalar_one_or_none.return_value = waarde
    resultaat.scalar_one.return_value = waarde
    return resultaat


@pytest.mark.asyncio
async def test_een_curator_van_een_andere_tenant_kan_geen_export_maken() -> None:
    with patch.object(archief, "public_tenant_scope", _scope(_tenant(5))):
        with pytest.raises(HTTPException) as fout:
            await archief.create_archive_export(
                tenantSlug="ketikoti", current_user=_gebruiker(6), session=AsyncMock()
            )

    assert fout.value.status_code == 403


@pytest.mark.asyncio
async def test_een_curator_van_een_andere_tenant_ziet_de_lijst_niet() -> None:
    with patch.object(archief, "public_tenant_scope", _scope(_tenant(5))):
        with pytest.raises(HTTPException) as fout:
            await archief.list_archive_exports(
                tenantSlug="ketikoti", limit=50, offset=0, current_user=_gebruiker(6), session=AsyncMock()
            )

    assert fout.value.status_code == 403


@pytest.mark.asyncio
async def test_een_curator_van_een_andere_tenant_kan_niet_downloaden() -> None:
    with patch.object(archief, "public_tenant_scope", _scope(_tenant(5))):
        with pytest.raises(HTTPException) as fout:
            await archief.download_archive_export(
                tenantSlug="ketikoti", export_id=1, current_user=_gebruiker(6), session=AsyncMock()
            )

    assert fout.value.status_code == 403


@pytest.mark.asyncio
async def test_een_export_id_van_een_andere_tenant_geeft_404() -> None:
    sessie = AsyncMock()
    sessie.execute.return_value = _uitslag(None)

    with patch.object(archief, "public_tenant_scope", _scope(_tenant(5))):
        with pytest.raises(HTTPException) as fout:
            await archief.download_archive_export(
                tenantSlug="ketikoti", export_id=77, current_user=_gebruiker(5), session=sessie
            )

    assert fout.value.status_code == 404


@pytest.mark.asyncio
async def test_de_downloadquery_filtert_op_de_eigen_tenant() -> None:
    sessie = AsyncMock()
    sessie.execute.return_value = _uitslag(None)

    with patch.object(archief, "public_tenant_scope", _scope(_tenant(5))):
        with pytest.raises(HTTPException):
            await archief.download_archive_export(
                tenantSlug="ketikoti", export_id=77, current_user=_gebruiker(5), session=sessie
            )

    sql = str(sessie.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "foundation_archive_exports.tenant_id = 5" in sql


@pytest.mark.asyncio
async def test_een_bezoeker_is_geen_curator() -> None:
    with pytest.raises(HTTPException) as fout:
        await require_curator(user=_gebruiker(5, PortalRole.VISITOR))

    assert fout.value.status_code == 403


@pytest.mark.asyncio
async def test_een_tweede_export_binnen_een_minuut_wordt_geweigerd() -> None:
    sessie = AsyncMock()
    sessie.execute.return_value = _uitslag(_NU - timedelta(seconds=10))

    with (
        patch.object(archief, "public_tenant_scope", _scope(_tenant(5))),
        patch.object(archief, "utc_now", return_value=_NU),
    ):
        with pytest.raises(HTTPException) as fout:
            await archief.create_archive_export(
                tenantSlug="ketikoti", current_user=_gebruiker(5), session=sessie
            )

    assert fout.value.status_code == 429


@pytest.mark.asyncio
async def test_een_mislukte_export_geeft_een_vaste_tekst_en_rolt_terug() -> None:
    sessie = AsyncMock()
    sessie.execute.return_value = _uitslag(None)
    dienst = MagicMock()
    dienst.export = AsyncMock(side_effect=archief.ArchiveExportError("intern: /pad/naar/x.jpg"))

    with (
        patch.object(archief, "public_tenant_scope", _scope(_tenant(5))),
        patch.object(archief, "FoundationArchiveService", return_value=dienst),
    ):
        with pytest.raises(HTTPException) as fout:
            await archief.create_archive_export(
                tenantSlug="ketikoti", current_user=_gebruiker(5), session=sessie
            )

    assert (fout.value.status_code, "/pad" in str(fout.value.detail), sessie.rollback.await_count) == (
        500,
        False,
        1,
    )


@pytest.mark.asyncio
async def test_een_beschadigd_pakket_geeft_409_bij_download() -> None:
    export = FoundationArchiveExport(
        id=1, tenant_id=5, bag_name="b", item_count=1, payload_file_count=1, size_bytes=3,
        sha256="0" * 64, storage_url="/uploads/foundation-archief/5/b.zip", trigger="handmatig",
    )
    sessie = AsyncMock()
    sessie.execute.return_value = _uitslag(export)
    dienst = MagicMock()
    dienst.read_archive = AsyncMock(side_effect=archief.ArchiveExportError("wijkt af"))

    with (
        patch.object(archief, "public_tenant_scope", _scope(_tenant(5))),
        patch.object(archief, "FoundationArchiveService", return_value=dienst),
    ):
        with pytest.raises(HTTPException) as fout:
            await archief.download_archive_export(
                tenantSlug="ketikoti", export_id=1, current_user=_gebruiker(5), session=sessie
            )

    assert fout.value.status_code == 409


def test_elke_archiefroute_eist_de_curatorrol() -> None:
    """Vangt het weghalen van `Depends(require_curator)` op een route (Gate 2 ronde 2, LOW-A)."""
    routes = [r for r in archief.router.routes if isinstance(r, APIRoute)]
    zonder = [
        r.path for r in routes if require_curator not in {d.call for d in r.dependant.dependencies}
    ]

    assert (len(routes), zonder) == (3, [])


@pytest.mark.asyncio
async def test_de_lijstquery_filtert_op_de_eigen_tenant() -> None:
    telling = _uitslag(0)
    rijen = MagicMock()
    rijen.scalars.return_value.all.return_value = []
    sessie = AsyncMock()
    sessie.execute.side_effect = [telling, rijen]

    with patch.object(archief, "public_tenant_scope", _scope(_tenant(5))):
        await archief.list_archive_exports(
            tenantSlug="ketikoti", limit=50, offset=0, current_user=_gebruiker(5), session=sessie
        )

    sql = str(sessie.execute.call_args_list[1].args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "foundation_archive_exports.tenant_id = 5" in sql


@pytest.mark.asyncio
async def test_een_mislukte_commit_verwijdert_het_pakket() -> None:
    from sqlalchemy.exc import OperationalError

    sessie = AsyncMock()
    sessie.execute.return_value = _uitslag(None)
    sessie.commit.side_effect = OperationalError("commit", {}, Exception("db weg"))
    export = FoundationArchiveExport(
        id=1, tenant_id=5, bag_name="b", item_count=1, payload_file_count=1, size_bytes=3,
        sha256="0" * 64, storage_url="/uploads/foundation-archief/5/b.zip", trigger="handmatig",
    )
    dienst = MagicMock()
    dienst.export = AsyncMock(return_value=export)
    dienst.discard = AsyncMock()

    with (
        patch.object(archief, "public_tenant_scope", _scope(_tenant(5))),
        patch.object(archief, "FoundationArchiveService", return_value=dienst),
    ):
        with pytest.raises(HTTPException):
            await archief.create_archive_export(
                tenantSlug="ketikoti", current_user=_gebruiker(5), session=sessie
            )

    dienst.discard.assert_awaited_once_with(export)
