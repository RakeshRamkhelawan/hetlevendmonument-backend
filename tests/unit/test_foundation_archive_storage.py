"""Opslag van archiefpakketten en teruglezen per tenant (BE-EP-054, Gate 2 M3/M1/MEDIUM-3).

Echte `FoundationStorageService` met de lokale backend in een tijdelijke map; geen mocks.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from src.core.services.foundation_storage import FoundationStorageError, FoundationStorageService
from src.core.shared.config import Settings


def _lokaal(tmp_path: Path) -> FoundationStorageService:
    instellingen = SimpleNamespace(
        storage_backend="local",
        local_upload_dir=str(tmp_path),
        foundation_blob_container="foundation",
        azure_storage_connection_string=None,
        max_upload_size_bytes=50 * 1024 * 1024,
    )
    return FoundationStorageService(settings=cast(Settings, instellingen))


def _azure() -> FoundationStorageService:
    instellingen = SimpleNamespace(
        storage_backend="azure",
        local_upload_dir="/tmp",
        foundation_blob_container="foundation",
        azure_storage_connection_string=None,
        max_upload_size_bytes=50 * 1024 * 1024,
    )
    return FoundationStorageService(settings=cast(Settings, instellingen))


@pytest.mark.asyncio
async def test_een_opgeslagen_archief_is_terug_te_lezen(tmp_path: Path) -> None:
    opslag = _lokaal(tmp_path)

    url = await opslag.upload_archive(tenant_id=5, bag_name="levendmonument-x-1", data=b"zip")

    assert await opslag.read_bytes(url, tenant_id=5) == b"zip"


@pytest.mark.asyncio
async def test_twee_archieven_met_dezelfde_naam_overschrijven_elkaar_niet(tmp_path: Path) -> None:
    opslag = _lokaal(tmp_path)

    eerste = await opslag.upload_archive(tenant_id=5, bag_name="zelfde", data=b"een")
    tweede = await opslag.upload_archive(tenant_id=5, bag_name="zelfde", data=b"twee")

    assert await opslag.read_bytes(eerste, tenant_id=5) == b"een" and eerste != tweede


@pytest.mark.asyncio
async def test_een_archief_van_een_andere_tenant_wordt_niet_gelezen(tmp_path: Path) -> None:
    opslag = _lokaal(tmp_path)
    url = await opslag.upload_archive(tenant_id=5, bag_name="geheim", data=b"zip")

    with pytest.raises(FoundationStorageError):
        await opslag.read_bytes(url, tenant_id=6)


@pytest.mark.asyncio
async def test_een_pad_met_dubbele_punten_wordt_geweigerd(tmp_path: Path) -> None:
    with pytest.raises(FoundationStorageError):
        await _lokaal(tmp_path).read_bytes("/uploads/foundation/5/../6/x.jpg", tenant_id=5)


@pytest.mark.asyncio
async def test_een_terugsprong_naar_een_bestaand_archief_van_een_andere_tenant_faalt(
    tmp_path: Path,
) -> None:
    """Het bestand van tenant 6 BESTAAT; alleen de padcontrole houdt tenant 5 tegen."""
    opslag = _lokaal(tmp_path)
    url = await opslag.upload_archive(tenant_id=6, bag_name="van-zes", data=b"geheim")
    via_terugsprong = url.replace("/foundation-archief/6/", "/foundation-archief/5/../6/")

    with pytest.raises(FoundationStorageError):
        await opslag.read_bytes(via_terugsprong, tenant_id=5)


@pytest.mark.asyncio
async def test_een_pad_buiten_de_foundation_opslag_wordt_geweigerd(tmp_path: Path) -> None:
    with pytest.raises(FoundationStorageError):
        await _lokaal(tmp_path).read_bytes("/uploads/andere/5/x.jpg", tenant_id=5)


@pytest.mark.asyncio
async def test_een_bag_naam_met_een_schuine_streep_wordt_geweigerd(tmp_path: Path) -> None:
    with pytest.raises(FoundationStorageError):
        await _lokaal(tmp_path).upload_archive(tenant_id=5, bag_name="a/b", data=b"zip")


@pytest.mark.asyncio
async def test_azure_weigert_een_url_buiten_de_container() -> None:
    url = "https://acct.blob.core.windows.net/anders/foundation/5/1/x.jpg"

    with pytest.raises(FoundationStorageError):
        await _azure().read_bytes(url, tenant_id=5)


@pytest.mark.asyncio
async def test_azure_weigert_een_blob_van_een_andere_tenant() -> None:
    url = "https://acct.blob.core.windows.net/foundation/foundation/6/1/x.jpg"

    with pytest.raises(FoundationStorageError):
        await _azure().read_bytes(url, tenant_id=5)


@pytest.mark.asyncio
async def test_azure_weigert_een_gecodeerde_terugsprong() -> None:
    url = "https://acct.blob.core.windows.net/foundation/foundation/5/%2E%2E/6/x.jpg"

    with pytest.raises(FoundationStorageError):
        await _azure().read_bytes(url, tenant_id=5)


@pytest.mark.asyncio
async def test_een_verweesd_archief_kan_worden_verwijderd(tmp_path: Path) -> None:
    opslag = _lokaal(tmp_path)
    url = await opslag.upload_archive(tenant_id=5, bag_name="weg", data=b"zip")

    await opslag.delete_archive(url, tenant_id=5)

    with pytest.raises(FoundationStorageError):
        await opslag.read_bytes(url, tenant_id=5)
