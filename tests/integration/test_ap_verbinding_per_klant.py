"""De ActivePieces-verbinding per klant, tegen een ECHTE PostgreSQL (ADR-040 B3, brief dag 2).

Wat hier gemeten wordt, en niet met dubbelgangers:

- een tenant zonder rij krijgt een 409-fout, een tenant met een rij precies ZIJN verbinding;
- het wachtwoord staat in de database VERSLEUTELD (de ruwe kolom is niet de leesbare tekst) en
  komt na het lezen weer leesbaar terug, alleen voor de tenant die het opsloeg;
- zonder `MASTER_ENCRYPTION_KEY` start het schrijven en het lezen niet stil op;
- de beheerroute is er alleen voor een platformbeheerder, en het wachtwoord komt er nooit uit
  (niet in het antwoord, niet in de auditregel).

Vereist de testdatabase op poort 5455 (`postgres_session`).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.activepieces.verbinding import ApVerbindingOntbreektError, ap_verbinding_voor
from src.core.activepieces.verbinding_beheer import ApVerbindingBeheer
from src.core.models.rbac_models import Tenant
from src.core.models.tenant_ap_verbinding_models import TenantAPVerbinding
from src.core.repositories.tenant_ap_verbinding_repository import TenantAPVerbindingRepository
from src.core.security.tenant_secret_encryption import HoofdsleutelOntbreekt, TenantSecretEncryption

pytestmark = pytest.mark.integration

_SLEUTEL = "Zq3vK8mWp2Xr9TnL5bYc7HfA1dGeJ4sUoI6xNzMwQvE"
_WACHTWOORD = "ap-wachtwoord-voor-de-test-9f3k"
_AUDIT = "src.core.api.v1.admin.ap_verbinding_router.schrijf_ap_verbinding_audit"


@pytest.fixture(autouse=True)
def _hoofdsleutel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", _SLEUTEL)


async def _maak_tenant(db: AsyncSession) -> int:
    kenmerk = uuid.uuid4().hex[:12]
    tenant = Tenant(name=f"ap-per-klant-{kenmerk}", slug=f"ap-per-klant-{kenmerk}")
    db.add(tenant)
    await db.flush()
    return int(tenant.id)


def _beheer(db: AsyncSession) -> ApVerbindingBeheer:
    return ApVerbindingBeheer(
        opslag=TenantAPVerbindingRepository(db), encryptie=TenantSecretEncryption()
    )


async def _leg_vast(db: AsyncSession, tenant_id: int, project: str = "proj-a") -> None:
    await _beheer(db).leg_vast(
        tenant_id,
        base_url="http://localhost:8081/api/v1",
        email=f"ap-{tenant_id}@example.test",
        wachtwoord=_WACHTWOORD,
        project_id=project,
    )


@pytest.mark.asyncio
async def test_een_tenant_zonder_rij_krijgt_een_409(postgres_session: AsyncSession) -> None:
    tenant_id = await _maak_tenant(postgres_session)

    with pytest.raises(ApVerbindingOntbreektError) as fout:
        await ap_verbinding_voor(tenant_id, postgres_session)

    assert fout.value.status_code == 409


@pytest.mark.asyncio
async def test_een_tenant_met_een_rij_krijgt_precies_zijn_verbinding(
    postgres_session: AsyncSession,
) -> None:
    tenant_a = await _maak_tenant(postgres_session)
    tenant_b = await _maak_tenant(postgres_session)
    await _leg_vast(postgres_session, tenant_a, project="proj-a")
    await _leg_vast(postgres_session, tenant_b, project="proj-b")

    verbinding = await ap_verbinding_voor(tenant_a, postgres_session)

    assert (verbinding.tenant_id, verbinding.project_id) == (tenant_a, "proj-a")


@pytest.mark.asyncio
async def test_een_tenant_zonder_rij_krijgt_niet_de_verbinding_van_een_ander(
    postgres_session: AsyncSession,
) -> None:
    tenant_a = await _maak_tenant(postgres_session)
    tenant_c = await _maak_tenant(postgres_session)
    await _leg_vast(postgres_session, tenant_a)

    with pytest.raises(ApVerbindingOntbreektError):
        await ap_verbinding_voor(tenant_c, postgres_session)


@pytest.mark.asyncio
async def test_het_wachtwoord_staat_versleuteld_in_de_database(
    postgres_session: AsyncSession,
) -> None:
    tenant_id = await _maak_tenant(postgres_session)
    await _leg_vast(postgres_session, tenant_id)

    ruw = (
        await postgres_session.execute(
            select(TenantAPVerbinding.wachtwoord_encrypted).where(
                TenantAPVerbinding.tenant_id == tenant_id
            )
        )
    ).scalar_one()

    assert _WACHTWOORD not in ruw and ruw.startswith("v1:")


@pytest.mark.asyncio
async def test_het_wachtwoord_komt_leesbaar_terug_voor_de_eigen_tenant(
    postgres_session: AsyncSession,
) -> None:
    tenant_id = await _maak_tenant(postgres_session)
    await _leg_vast(postgres_session, tenant_id)

    verbinding = await ap_verbinding_voor(tenant_id, postgres_session)

    assert verbinding.wachtwoord == _WACHTWOORD


@pytest.mark.asyncio
async def test_het_wachtwoord_staat_niet_in_de_weergave_van_de_gelezen_verbinding(
    postgres_session: AsyncSession,
) -> None:
    tenant_id = await _maak_tenant(postgres_session)
    await _leg_vast(postgres_session, tenant_id)

    verbinding = await ap_verbinding_voor(tenant_id, postgres_session)

    assert _WACHTWOORD not in repr(verbinding)


@pytest.mark.asyncio
async def test_zonder_hoofdsleutel_start_het_lezen_niet_stil_op(
    postgres_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant_id = await _maak_tenant(postgres_session)
    await _leg_vast(postgres_session, tenant_id)
    monkeypatch.delenv("MASTER_ENCRYPTION_KEY")

    with pytest.raises(HoofdsleutelOntbreekt):
        await ap_verbinding_voor(tenant_id, postgres_session)


@pytest.mark.asyncio
async def test_een_rij_die_met_de_sleutel_van_een_andere_tenant_is_gemaakt_wordt_geweigerd(
    postgres_session: AsyncSession,
) -> None:
    tenant_a = await _maak_tenant(postgres_session)
    tenant_b = await _maak_tenant(postgres_session)
    await TenantAPVerbindingRepository(postgres_session).upsert(
        tenant_a,
        "http://localhost:8081/api/v1",
        "ap@example.test",
        TenantSecretEncryption().encrypt(tenant_b, _WACHTWOORD),
        "proj-a",
    )

    with pytest.raises(ApVerbindingOntbreektError):
        await ap_verbinding_voor(tenant_a, postgres_session)


# --------------------------------------------------------------------------------------------
# De beheerroute
# --------------------------------------------------------------------------------------------


def _gebruiker(*, superuser: bool, tenant_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        email="beheer@example.test",
        tenant_id=tenant_id,
        roles=["admin"],
        scopes=[],
        is_superuser=superuser,
        is_active=True,
    )


@pytest_asyncio.fixture
async def beheerroute(postgres_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    from src.core.api.v1.admin.ap_verbinding_router import router
    from src.core.api.v1.admin.dependencies import get_current_user, get_db

    app = FastAPI()
    app.include_router(router)
    app.state.gebruiker = _gebruiker(superuser=True)
    app.dependency_overrides[get_db] = lambda: postgres_session
    app.dependency_overrides[get_current_user] = lambda: app.state.gebruiker
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.app = app  # type: ignore[attr-defined]
        yield client


def _body(**extra: object) -> dict[str, object]:
    return {
        "base_url": "http://localhost:8081/api/v1",
        "email": "ap@example.test",
        "wachtwoord": _WACHTWOORD,
        "project_id": "proj-a",
        **extra,
    }


@pytest.mark.asyncio
async def test_een_platformbeheerder_legt_een_verbinding_vast(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    tenant_id = await _maak_tenant(postgres_session)

    with patch(_AUDIT, new=AsyncMock()):
        antwoord = await beheerroute.put(f"/admin/tenants/{tenant_id}/ap-verbinding", json=_body())

    assert antwoord.status_code == 200, antwoord.text


@pytest.mark.asyncio
async def test_een_tenantbeheerder_die_geen_platformbeheerder_is_krijgt_403(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    tenant_id = await _maak_tenant(postgres_session)
    beheerroute.app.state.gebruiker = _gebruiker(superuser=False, tenant_id=tenant_id)  # type: ignore[attr-defined]

    antwoord = await beheerroute.put(f"/admin/tenants/{tenant_id}/ap-verbinding", json=_body())

    assert antwoord.status_code == 403, antwoord.text


@pytest.mark.asyncio
async def test_een_tenantbeheerder_legt_niets_vast(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    tenant_id = await _maak_tenant(postgres_session)
    beheerroute.app.state.gebruiker = _gebruiker(superuser=False, tenant_id=tenant_id)  # type: ignore[attr-defined]

    await beheerroute.put(f"/admin/tenants/{tenant_id}/ap-verbinding", json=_body())

    assert await TenantAPVerbindingRepository(postgres_session).get(tenant_id) is None


@pytest.mark.asyncio
async def test_het_antwoord_bevat_het_wachtwoord_niet(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    tenant_id = await _maak_tenant(postgres_session)

    with patch(_AUDIT, new=AsyncMock()):
        antwoord = await beheerroute.put(f"/admin/tenants/{tenant_id}/ap-verbinding", json=_body())

    assert _WACHTWOORD not in antwoord.text


@pytest.mark.asyncio
async def test_het_lezen_toont_alleen_dat_er_een_wachtwoord_is(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    tenant_id = await _maak_tenant(postgres_session)
    await _leg_vast(postgres_session, tenant_id)

    antwoord = await beheerroute.get(f"/admin/tenants/{tenant_id}/ap-verbinding")

    assert antwoord.json()["data"]["heeft_wachtwoord"] is True and _WACHTWOORD not in antwoord.text


@pytest.mark.asyncio
async def test_de_auditregel_bevat_het_wachtwoord_niet(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    tenant_id = await _maak_tenant(postgres_session)

    with patch(_AUDIT, new=AsyncMock()) as audit:
        await beheerroute.put(f"/admin/tenants/{tenant_id}/ap-verbinding", json=_body())

    assert audit.await_args is not None and _WACHTWOORD not in repr(audit.await_args)


@pytest.mark.asyncio
async def test_een_tenant_id_in_de_body_wordt_geweigerd(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    tenant_id = await _maak_tenant(postgres_session)

    antwoord = await beheerroute.put(
        f"/admin/tenants/{tenant_id}/ap-verbinding", json=_body(tenant_id=999)
    )

    assert antwoord.status_code == 422, antwoord.text


@pytest.mark.asyncio
async def test_een_onversleuteld_adres_naar_een_publieke_host_wordt_geweigerd(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    tenant_id = await _maak_tenant(postgres_session)
    body = _body(base_url="http://ap.example.com/api/v1")

    with patch(_AUDIT, new=AsyncMock()):
        antwoord = await beheerroute.put(f"/admin/tenants/{tenant_id}/ap-verbinding", json=body)

    assert antwoord.status_code == 400, antwoord.text


@pytest.mark.asyncio
async def test_een_adres_met_inloggegevens_wordt_geweigerd(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    tenant_id = await _maak_tenant(postgres_session)
    body = _body(base_url="https://gebruiker:geheim@ap.example.com/api/v1")

    with patch(_AUDIT, new=AsyncMock()):
        antwoord = await beheerroute.put(f"/admin/tenants/{tenant_id}/ap-verbinding", json=body)

    assert antwoord.status_code == 400, antwoord.text


@pytest.mark.asyncio
async def test_een_onbekende_tenant_geeft_404(beheerroute: AsyncClient) -> None:
    with patch(_AUDIT, new=AsyncMock()):
        antwoord = await beheerroute.put("/admin/tenants/987654321/ap-verbinding", json=_body())

    assert antwoord.status_code == 404, antwoord.text


@pytest.mark.asyncio
async def test_een_tweede_tenant_met_hetzelfde_adres_en_project_krijgt_409_zonder_de_ander_te_noemen(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    eerste = await _maak_tenant(postgres_session)
    tweede = await _maak_tenant(postgres_session)
    await _leg_vast(postgres_session, eerste, project="proj-gedeeld")

    with patch(_AUDIT, new=AsyncMock()):
        antwoord = await beheerroute.put(
            f"/admin/tenants/{tweede}/ap-verbinding", json=_body(project_id="proj-gedeeld")
        )

    assert antwoord.status_code == 409 and str(eerste) not in antwoord.text, antwoord.text


@pytest.mark.asyncio
async def test_een_gelijktijdige_tweede_put_voor_dezelfde_tenant_geeft_409_en_niet_tenant_bestaat_niet(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    from sqlalchemy.exc import IntegrityError

    tenant_id = await _maak_tenant(postgres_session)
    botsing = IntegrityError(
        "INSERT ...",
        {},
        Exception('duplicate key value violates unique constraint "uq_tenant_ap_verbindingen_tenant"'),
    )

    with (
        patch(_AUDIT, new=AsyncMock()),
        patch(
            "src.core.activepieces.verbinding_beheer.ApVerbindingBeheer.leg_vast",
            new=AsyncMock(side_effect=botsing),
        ),
    ):
        antwoord = await beheerroute.put(f"/admin/tenants/{tenant_id}/ap-verbinding", json=_body())

    assert antwoord.status_code == 409, antwoord.text


@pytest.mark.asyncio
async def test_een_gelijktijdige_tweede_put_laat_een_auditregel_achter(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    from sqlalchemy.exc import IntegrityError

    tenant_id = await _maak_tenant(postgres_session)
    botsing = IntegrityError(
        "INSERT ...",
        {},
        Exception('duplicate key value violates unique constraint "uq_tenant_ap_verbindingen_tenant"'),
    )

    with (
        patch(_AUDIT, new=AsyncMock()) as audit,
        patch(
            "src.core.activepieces.verbinding_beheer.ApVerbindingBeheer.leg_vast",
            new=AsyncMock(side_effect=botsing),
        ),
    ):
        await beheerroute.put(f"/admin/tenants/{tenant_id}/ap-verbinding", json=_body())

    assert audit.await_args is not None and "gelijktijdige_wijziging" in repr(audit.await_args)


@pytest.mark.asyncio
async def test_een_vreemde_sleutelfout_van_een_andere_tabel_wordt_niet_als_tenant_bestaat_niet_verkocht(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    from sqlalchemy.exc import IntegrityError

    tenant_id = await _maak_tenant(postgres_session)
    andere = IntegrityError(
        "INSERT ...",
        {},
        Exception('insert violates foreign key constraint "andere_tabel_kolom_fkey"'),
    )

    with (
        patch(_AUDIT, new=AsyncMock()),
        patch(
            "src.core.activepieces.verbinding_beheer.ApVerbindingBeheer.leg_vast",
            new=AsyncMock(side_effect=andere),
        ),
    ):
        with pytest.raises(IntegrityError):
            await beheerroute.put(f"/admin/tenants/{tenant_id}/ap-verbinding", json=_body())


@pytest.mark.asyncio
async def test_een_onbekende_integriteitsfout_wordt_niet_als_tenant_bestaat_niet_verkocht(
    beheerroute: AsyncClient, postgres_session: AsyncSession
) -> None:
    from sqlalchemy.exc import IntegrityError

    tenant_id = await _maak_tenant(postgres_session)
    vreemd = IntegrityError("INSERT ...", {}, Exception("iets heel anders ging mis"))

    with (
        patch(_AUDIT, new=AsyncMock()),
        patch(
            "src.core.activepieces.verbinding_beheer.ApVerbindingBeheer.leg_vast",
            new=AsyncMock(side_effect=vreemd),
        ),
    ):
        with pytest.raises(IntegrityError):
            await beheerroute.put(f"/admin/tenants/{tenant_id}/ap-verbinding", json=_body())
