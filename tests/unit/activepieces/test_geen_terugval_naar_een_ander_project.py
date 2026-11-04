"""Een tenant zonder eigen ActivePieces-verbinding of -project krijgt een fout, nooit een ander bedrijf.

Brief 2026-10-20 (dag 1) en 2026-10-21 (dag 2), ADR-040 B3/B4.

**Wat er stond.** `ActivePiecesClient.find_project_for_tenant` gaf `projects[0]` -- het EERSTE project
op de server, dus het project van een willekeurig ander bedrijf -- of de tekst `"default"`.
`tenant_utils.get_tenant_ap_project` viel bij elke fout terug op `str(tenant_id)`. En de client las
een algemene URL en een algemeen wachtwoord, voor elke tenant dezelfde.

**Wat deze tests bewaken.** De verbinding van een tenant komt uit EEN plek (`ap_verbinding_voor`):
de rij van die tenant in `tenant_ap_verbindingen`, met het wachtwoord versleuteld met de sleutel van
die tenant. Ontbreekt de rij, of is het wachtwoord niet te lezen, dan is dat een duidelijke
Nederlandse fout. Zonder hoofdsleutel faalt het lezen luid. De opslag zelf (echte database) staat in
`tests/integration/test_ap_verbinding_per_klant.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.activepieces.verbinding import (
    ApProjectIsNietVanDezeKlantError,
    ApVerbinding,
    ApVerbindingOntbreektError,
    ap_verbinding_voor,
)
from src.core.repositories.tenant_ap_verbinding_repository import OpgeslagenAPVerbinding
from src.core.security.tenant_secret_encryption import HoofdsleutelOntbreekt, TenantSecretEncryption

_SLEUTEL = "Zq3vK8mWp2Xr9TnL5bYc7HfA1dGeJ4sUoI6xNzMwQvE"
_REPO_GET = (
    "src.core.repositories.tenant_ap_verbinding_repository.TenantAPVerbindingRepository.get"
)
_ADOPT = "src.core.database.bypass_session.adopt_tenant"


@pytest.fixture(autouse=True)
def _hoofdsleutel(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", _SLEUTEL)
    yield


@asynccontextmanager
async def _geen_rls(db: object, tenant_id: int) -> AsyncIterator[None]:
    yield


def _rij(
    tenant_id: int = 7,
    *,
    project_id: str = "proj-7",
    wachtwoord: str = "geheim-voor-de-test",
    versleuteld_voor: int | None = None,
) -> OpgeslagenAPVerbinding:
    nu = datetime.now(timezone.utc)
    return OpgeslagenAPVerbinding(
        id=1,
        tenant_id=tenant_id,
        base_url="http://localhost:8080/api/v1",
        email="ap@example.test",
        wachtwoord_encrypted=TenantSecretEncryption().encrypt(
            versleuteld_voor or tenant_id, wachtwoord
        ),
        project_id=project_id,
        created_at=nu,
        updated_at=nu,
    )


def _verbinding(tenant_id: int = 7, project_id: str = "proj-7") -> ApVerbinding:
    return ApVerbinding(
        tenant_id=tenant_id,
        base_url="http://ap.example.test/api/v1",
        email="ap@example.test",
        wachtwoord="geheim-voor-de-test",
        project_id=project_id,
    )


async def _lees(tenant_id: int, rij: OpgeslagenAPVerbinding | None) -> ApVerbinding:
    with patch(_REPO_GET, new=AsyncMock(return_value=rij)), patch(_ADOPT, _geen_rls):
        return await ap_verbinding_voor(tenant_id, MagicMock())


@pytest.mark.asyncio
async def test_een_tenant_zonder_rij_krijgt_een_fout() -> None:
    with pytest.raises(ApVerbindingOntbreektError) as fout:
        await _lees(8, None)

    assert fout.value.status_code == 409


@pytest.mark.asyncio
async def test_een_tenant_met_een_rij_krijgt_de_verbinding_van_precies_die_tenant() -> None:
    verbinding = await _lees(7, _rij(7, project_id="proj-7"))

    assert (verbinding.tenant_id, verbinding.project_id) == (7, "proj-7")


@pytest.mark.asyncio
async def test_het_wachtwoord_wordt_ontsleuteld_voor_het_gebruik() -> None:
    verbinding = await _lees(7, _rij(7, wachtwoord="geheim-voor-de-test"))

    assert verbinding.wachtwoord == "geheim-voor-de-test"


@pytest.mark.asyncio
async def test_een_wachtwoord_van_een_andere_tenant_geeft_dezelfde_fout_als_geen_rij() -> None:
    with pytest.raises(ApVerbindingOntbreektError):
        await _lees(7, _rij(7, versleuteld_voor=8))


@pytest.mark.asyncio
async def test_een_beschadigd_wachtwoord_geeft_een_fout_zonder_het_geheim_te_noemen() -> None:
    rij = _rij(7)
    kapot = OpgeslagenAPVerbinding(**{**rij.__dict__, "wachtwoord_encrypted": "v1:geen-token"})

    with pytest.raises(ApVerbindingOntbreektError) as fout:
        await _lees(7, kapot)

    assert "geheim-voor-de-test" not in fout.value.message


@pytest.mark.asyncio
async def test_zonder_hoofdsleutel_faalt_het_lezen_luid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASTER_ENCRYPTION_KEY", raising=False)

    with pytest.raises(HoofdsleutelOntbreekt):
        await _lees(7, _rij(7))


@pytest.mark.asyncio
async def test_de_foutmelding_is_nederlands_en_noemt_geen_geheim() -> None:
    with pytest.raises(ApVerbindingOntbreektError) as fout:
        await _lees(8, None)

    assert "workflowbuilder" in fout.value.message.lower()


def test_het_wachtwoord_staat_niet_in_de_weergave_van_de_verbinding() -> None:
    assert "geheim-voor-de-test" not in repr(_verbinding())


@pytest.mark.asyncio
async def test_het_project_van_een_tenant_zonder_verbinding_wordt_niet_geraden() -> None:
    from src.core.activepieces.tenant_utils import get_tenant_ap_project

    with patch(_REPO_GET, new=AsyncMock(return_value=None)), patch(_ADOPT, _geen_rls):
        with patch(
            "src.core.database.database.get_async_session", _eigen_sessie
        ), pytest.raises(ApVerbindingOntbreektError):
            await get_tenant_ap_project(5)


@asynccontextmanager
async def _eigen_sessie() -> AsyncIterator[MagicMock]:
    yield MagicMock()


@pytest.mark.asyncio
async def test_het_project_van_een_tenant_met_verbinding_komt_uit_zijn_rij() -> None:
    from src.core.activepieces.tenant_utils import get_tenant_ap_project

    with patch(_REPO_GET, new=AsyncMock(return_value=_rij(5, project_id="proj-5"))), patch(
        _ADOPT, _geen_rls
    ), patch("src.core.database.database.get_async_session", _eigen_sessie):
        assert await get_tenant_ap_project(5) == "proj-5"


def test_de_client_kan_niet_zonder_verbinding_worden_gemaakt() -> None:
    from src.core.activepieces.client import ActivePiecesClient

    with pytest.raises(TypeError):
        ActivePiecesClient()  # type: ignore[call-arg]


def test_de_client_heeft_geen_zoekfunctie_meer_die_het_eerste_project_kiest() -> None:
    from src.core.activepieces.client import ActivePiecesClient

    assert not hasattr(ActivePiecesClient, "find_project_for_tenant")


@pytest.mark.asyncio
async def test_een_workflow_in_het_project_van_een_ander_bedrijf_wordt_geweigerd() -> None:
    from src.core.activepieces.client import ActivePiecesClient

    client = ActivePiecesClient(_verbinding())

    with pytest.raises(ApProjectIsNietVanDezeKlantError):
        await client.execute_workflow({"nodes": [], "edges": []}, project_id="proj-van-een-ander")


def test_het_eigen_project_wordt_toegestaan_en_none_betekent_het_eigen_project() -> None:
    from src.core.activepieces.client import ActivePiecesClient

    client = ActivePiecesClient(_verbinding())

    assert (client.eigen_project(None), client.eigen_project("proj-7")) == ("proj-7", "proj-7")


@pytest.mark.asyncio
async def test_een_flow_aanmaken_in_een_ander_project_wordt_geweigerd() -> None:
    from src.core.activepieces.client import ActivePiecesClient

    client = ActivePiecesClient(_verbinding())

    with pytest.raises(ApProjectIsNietVanDezeKlantError):
        await client.create_flow("proj-van-een-ander", {"displayName": "x"})


@pytest.mark.asyncio
async def test_flows_lezen_uit_een_ander_project_wordt_geweigerd() -> None:
    from src.core.activepieces.client import ActivePiecesClient

    client = ActivePiecesClient(_verbinding())

    with pytest.raises(ApProjectIsNietVanDezeKlantError):
        await client.list_project_flows("proj-van-een-ander")


@pytest.mark.asyncio
async def test_een_verbinding_aanmaken_in_een_ander_project_wordt_geweigerd() -> None:
    from src.core.activepieces.client import ActivePiecesClient
    from src.core.activepieces.schemas import ConnectionCreate
    from src.core.activepieces.service import ActivePiecesService

    service = ActivePiecesService(client=ActivePiecesClient(_verbinding()))
    data = ConnectionCreate(
        name="n", app_name="slack", project_id="proj-van-een-ander", value={"token": "x"}
    )

    with pytest.raises(ApProjectIsNietVanDezeKlantError):
        await service.create_connection(data)


@pytest.mark.asyncio
async def test_de_service_maakt_geen_project_aan_en_kiest_het_project_van_de_client() -> None:
    from src.core.activepieces.client import ActivePiecesClient
    from src.core.activepieces.service import ActivePiecesService

    service = ActivePiecesService(client=ActivePiecesClient(_verbinding()))

    assert await service._get_or_create_project_for_tenant(7) == "proj-7"


@pytest.mark.asyncio
async def test_de_verbindingenlijst_toont_alleen_verbindingen_van_het_eigen_project() -> None:
    from unittest.mock import AsyncMock

    from src.core.activepieces.client import ActivePiecesClient
    from src.core.activepieces.service import ActivePiecesService

    client = ActivePiecesClient(_verbinding())
    antwoord = {
        "data": [
            {
                "id": "c1",
                "displayName": "eigen",
                "pieceName": "@activepieces/piece-slack",
                "projectIds": ["proj-7"],
                "created": "2026-01-01T00:00:00Z", "updated": "2026-01-01T00:00:00Z",
            },
            {
                "id": "c2",
                "displayName": "vreemd",
                "pieceName": "@activepieces/piece-slack",
                "projectIds": ["proj-van-een-ander"],
                "created": "2026-01-01T00:00:00Z", "updated": "2026-01-01T00:00:00Z",
            },
        ]
    }
    client._make_request = AsyncMock(return_value=antwoord)  # type: ignore[method-assign]

    lijst = await ActivePiecesService(client=client).list_connections()

    assert [c.id for c in lijst] == ["c1"]
    assert client._make_request.await_args.kwargs["params"]["projectId"] == "proj-7"


@pytest.mark.asyncio
async def test_een_service_zonder_tenant_krijgt_geen_algemene_client() -> None:
    from src.core.activepieces.service import _DisabledActivePiecesClient, activepieces_service_voor

    service = await activepieces_service_voor(None)

    assert isinstance(service._client, _DisabledActivePiecesClient)


@pytest.mark.asyncio
async def test_een_service_voor_een_tenant_zonder_verbinding_krijgt_de_uitgeschakelde_client() -> None:
    from src.core.activepieces.service import _DisabledActivePiecesClient, activepieces_service_voor

    with patch(_REPO_GET, new=AsyncMock(return_value=None)), patch(_ADOPT, _geen_rls), patch(
        "src.core.database.database.get_async_session", _eigen_sessie
    ):
        service = await activepieces_service_voor(8)

    assert isinstance(service._client, _DisabledActivePiecesClient)
