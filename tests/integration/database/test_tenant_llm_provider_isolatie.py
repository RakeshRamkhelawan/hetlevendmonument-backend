"""Tenantisolatie van de providerketen, tegen een ECHTE PostgreSQL.

**Waarom dit niet met mocks kan.** De unittests in
`tests/unit/services/test_tenant_llm_provider_service.py` gebruiken een dubbelganger voor de
repository. Die bewijzen dat de SERVICE het juiste vraagt, maar niet dat de DATABASE het juiste
teruggeeft: een vergeten `WHERE tenant_id = ...` is precies de fout die een dubbelganger niet
kan vertonen, omdat hij het filter nooit uitvoert. Backend-patterns regel 11 eist daarom een
isolatietest per repositorymethode, en die hoort tegen de echte engine te draaien.

**Waarom RLS hier niet het antwoord is.** De tabel heeft policies, maar de applicatie verbindt
als eigenaar van de tabellen en PostgreSQL past RLS niet toe op de eigenaar (ADR-036 OP-151,
gemeten). Het expliciete `tenant_id`-filter in de repository is vandaag dus de ENIGE laag, en
precies dat toetsen deze tests.

Vereist de testdatabase op netwerkpoort 5455:
`docker start sanskritisetuorg-postgres-test-1`.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Tenant
from src.core.repositories.tenant_llm_provider_repository import TenantLLMProviderRepository

pytestmark = pytest.mark.integration


async def _maak_tenant(db: AsyncSession, *, extern_toegestaan: bool) -> int:
    """Een verse tenant met een unieke naam.

    Uniek via `uuid4`, niet via een teller: `name` en `slug` staan onder een UNIQUE-constraint en
    de sessie rolt wel terug maar deelt de tabel met de andere tests in deze run.
    """
    kenmerk = uuid.uuid4().hex[:12]
    tenant = Tenant(
        name=f"llm-isolatie-{kenmerk}",
        slug=f"llm-isolatie-{kenmerk}",
        externe_providers_toegestaan=extern_toegestaan,
    )
    db.add(tenant)
    await db.flush()
    return int(tenant.id)


@pytest.mark.asyncio
async def test_alle_toont_alleen_de_eigen_rijen(postgres_session: AsyncSession) -> None:
    """Tenant A ziet de providerrij van tenant B NIET."""
    repo = TenantLLMProviderRepository(postgres_session)
    tenant_a = await _maak_tenant(postgres_session, extern_toegestaan=True)
    tenant_b = await _maak_tenant(postgres_session, extern_toegestaan=True)

    await repo.voeg_toe(
        tenant_a,
        volgorde=1,
        naam="provider-van-a",
        base_url="https://a.example.com/v1",
        model="model-a",
        api_key_encrypted="versleuteld-van-a",
    )
    await repo.voeg_toe(
        tenant_b,
        volgorde=1,
        naam="provider-van-b",
        base_url="https://b.example.com/v1",
        model="model-b",
        api_key_encrypted="versleuteld-van-b",
    )

    van_a = await repo.alle(tenant_a)

    assert [rij.naam for rij in van_a] == ["provider-van-a"]


@pytest.mark.asyncio
async def test_de_versleutelde_sleutel_van_de_ander_komt_nooit_mee(
    postgres_session: AsyncSession,
) -> None:
    """De sterkste vorm van de vorige test: geen enkel veld van B duikt op bij A."""
    repo = TenantLLMProviderRepository(postgres_session)
    tenant_a = await _maak_tenant(postgres_session, extern_toegestaan=True)
    tenant_b = await _maak_tenant(postgres_session, extern_toegestaan=True)

    await repo.voeg_toe(
        tenant_a,
        volgorde=1,
        naam="a",
        base_url="https://a.example.com/v1",
        model="m",
        api_key_encrypted=None,
    )
    await repo.voeg_toe(
        tenant_b,
        volgorde=1,
        naam="b",
        base_url="https://b.example.com/v1",
        model="m",
        api_key_encrypted="GEHEIM-VAN-B",
    )

    sleutels = [rij.api_key_encrypted for rij in await repo.alle(tenant_a)]

    assert "GEHEIM-VAN-B" not in sleutels


@pytest.mark.asyncio
async def test_actieve_filtert_op_tenant_en_op_de_kolom_actief(
    postgres_session: AsyncSession,
) -> None:
    """`actieve()` heeft twee voorwaarden; een ontbrekend tenantfilter valt hier door.

    Heette tot 2026-09-21 `..._en_op_de_vlag`. Die naam was dubbelzinnig: er zijn TWEE vlaggen
    in dit domein -- de kolom `actief` van de RIJ en `externe_providers_toegestaan` van de
    TENANT -- en deze test gaat over de eerste. Beide tenants staan hier op
    `extern_toegestaan=True`, dus wie op de oude naam afging, concludeerde ten onrechte dat de
    tweede vlag gedekt was. Een woord, een betekenis (CLAUDE.md).
    """
    repo = TenantLLMProviderRepository(postgres_session)
    tenant_a = await _maak_tenant(postgres_session, extern_toegestaan=True)
    tenant_b = await _maak_tenant(postgres_session, extern_toegestaan=True)

    await repo.voeg_toe(
        tenant_a, volgorde=1, naam="a-actief", base_url="https://a.example.com/v1", model="m"
    )
    await repo.voeg_toe(
        tenant_a,
        volgorde=2,
        naam="a-uit",
        base_url="https://a2.example.com/v1",
        model="m",
        actief=False,
    )
    await repo.voeg_toe(
        tenant_b, volgorde=1, naam="b-actief", base_url="https://b.example.com/v1", model="m"
    )

    namen = [rij.naam for rij in await repo.actieve(tenant_a)]

    assert namen == ["a-actief"]


@pytest.mark.asyncio
async def test_de_keten_komt_terug_op_volgorde(postgres_session: AsyncSession) -> None:
    """De failoverketen van ADR-026 IS de sortering op `volgorde`, niet de invoegvolgorde."""
    repo = TenantLLMProviderRepository(postgres_session)
    tenant = await _maak_tenant(postgres_session, extern_toegestaan=True)

    for volgorde, naam in ((3, "derde"), (1, "eerste"), (2, "tweede")):
        await repo.voeg_toe(
            tenant,
            volgorde=volgorde,
            naam=naam,
            base_url=f"https://{naam}.example.com/v1",
            model="m",
        )

    namen = [rij.naam for rij in await repo.actieve(tenant)]

    assert namen == ["eerste", "tweede", "derde"]


@pytest.mark.asyncio
async def test_mag_extern_leest_de_vlag_van_de_juiste_tenant(
    postgres_session: AsyncSession,
) -> None:
    """De schakelaar van de buurman mag nooit de eigen weigering opheffen."""
    tenant_uit = await _maak_tenant(postgres_session, extern_toegestaan=False)
    await _maak_tenant(postgres_session, extern_toegestaan=True)
    repo = TenantLLMProviderRepository(postgres_session)

    assert await repo.mag_extern(tenant_uit) is False


@pytest.mark.asyncio
async def test_een_onbekende_tenant_krijgt_geen_toestemming(
    postgres_session: AsyncSession,
) -> None:
    """Fail-secure: geen rij gevonden is FALSE, niet None-dat-waar-wordt."""
    repo = TenantLLMProviderRepository(postgres_session)

    assert await repo.mag_extern(2_147_483_600) is False


@pytest.mark.asyncio
async def test_de_auditregel_van_een_weigering_OVERLEEFT_een_rollback(
    postgres_session: AsyncSession,
) -> None:
    """Schrijven is niet hetzelfde als bewaren, en alleen een echte database bewijst welke.

    Dit is de tweede Gate 2-bevinding, en de reviewer eiste er terecht deze vorm van bewijs
    voor: `AuditService.log_event` doet alleen `flush()`, en `get_db` doet bij een
    `HTTPException` een `rollback()`. Een unittest die telt dat er gecommit IS, herhaalt de
    aanname; deze test rolt daadwerkelijk terug en kijkt of de rij er dan nog staat.

    De `rollback()` hieronder staat voor wat `get_db` doet zodra de router zijn 403 gooit.
    """
    from sqlalchemy import func

    from src.core.api.v1.admin.dependencies import schrijf_llm_provider_audit
    from src.core.governance.models import AuditLog

    tenant_id = await _maak_tenant(postgres_session, extern_toegestaan=False)
    kenmerk = f"LLM_PROVIDER_EXTERN_GEWEIGERD_{uuid.uuid4().hex[:8]}"

    await schrijf_llm_provider_audit(
        postgres_session,
        event_type=kenmerk,
        user_id=None,
        tenant_id=tenant_id,
        ip_address="127.0.0.1",
        request_method="POST",
        details={"reden": "externe_providers_niet_toegestaan"},
    )
    await postgres_session.rollback()

    aantal = await postgres_session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == kenmerk)
    )

    assert aantal == 1, (
        "de auditregel staat niet meer in de tabel na een rollback -- hij was geflusht maar "
        "nooit vastgelegd, en dat is precies de faalvorm die deze test moet vangen"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("ongeldig", [0, -1, True])
async def test_een_ongeldige_tenant_wordt_geweigerd_voor_de_query(
    postgres_session: AsyncSession, ongeldig: object
) -> None:
    """`True` staat hier met opzet bij: in Python is `isinstance(True, int)` waar.

    Zonder de expliciete bool-uitsluiting zou `mag_extern(True)` de rij van tenant 1 lezen.
    """
    repo = TenantLLMProviderRepository(postgres_session)

    with pytest.raises(ValueError):
        await repo.mag_extern(ongeldig)  # type: ignore[arg-type]
