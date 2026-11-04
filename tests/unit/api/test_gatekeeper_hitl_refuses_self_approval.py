"""De aanvrager mag zijn eigen gatekeeper-ticket niet goedkeuren (ADR-036 OP-81).

**Wat er gemeten is, en waarom de registerrij herzien moest worden.** OP-81 stond genoteerd als
"OPEN als vraag, niet als gat": `HITLRequestModel` (`src/core/governance/models.py`) heeft geen
enkel veld voor een menselijke aanvrager -- alleen `agent_id` en `task_id` -- dus de relatie "de
aanvrager keurt zichzelf goed" zou daar niet bestaan. Die meting klopt, maar de conclusie niet.
Het ticket wordt weliswaar door een AGENT aangemaakt, maar die agent handelt NAMENS een mens, en
dat is precies het geval waarvoor OWASP ASVS 5.0 V8 een expliciete eis heeft:

    ASVS 8.3.3 -- neem het autorisatiebesluit op basis van de permissies van het OORSPRONKELIJKE
    SUBJECT, niet van een tussenliggende service die namens hem handelt.

De ontbrekende kolom is dus geen reden om de grens niet te trekken; hij IS het gat. Het
zusteroppervlak `src/core/tool_broker/` doet het al goed: `HITLTicketRepository.create_hitl_request`
zet `_requested_by = str(user_id)` (de INITIERENDE MENS) en bewaart de agent apart als
`_executing_identity`, waarna `api/v1/tool_broker/hitl_router.py::_refuse_self_approval` op die
eerste vergelijkt. Twee identiteiten, en het besluit hangt aan de mens -- conform 8.3.3.

Dit bestand legt dezelfde grens op het gatekeeper-pad vast.

**Deze tests lopen over de ECHTE producent.** Het ticket wordt niet met de hand verzonnen: een
echte `Gatekeeper` evalueert een echte `TaskData`, levert een echte `HITLRequest` op, die door de
echte `GatekeeperRepository.save_hitl_request` in een echte databaserij wordt gezet. Pas daarna
gaat er een verzoek naar de echte route. Dat is met opzet: in dit project is twee keer eerder een
test groen gebleven die zijn eigen invoer aan beide kanten van de vergelijking verzon.

**Mutatiebewijs (verplicht, beide richtingen -- zie .claude/rules/quality-gates.md).** De gemeten
uitkomsten staan in `docs/backend/review/review-BE-SEC-049.md`; per mutatie is genoteerd hoeveel
tests slaagden en faalden:

1. `_refuse_self_approval` uit `approve_hitl` verwijderd -> de approve-test hieronder wordt ROOD.
2. Dezelfde regel uit `reject_hitl` verwijderd -> de reject-variant wordt ROOD.
3. De check verscherpt tot "weiger elke goedkeuring" -> `TestALegitimateApprovalStillWorks` wordt
   ROOD. Zonder deze helft is "weiger alles" een geldige oplossing.
4. `save_hitl_request` laat `requested_by_user_id` weg -> `TestTheRequesterIsRecorded` wordt ROOD
   en de zelf-goedkeuringstest valt stil terug op fail-open.

De OWASP Authorization Cheat Sheet eist dat autorisatielogica zowel unit- als integratietests
krijgt. Dit is de unit-helft (echte modellen, echte repository, echte route, SQLite in geheugen);
de Postgres-helft staat in `tests/integration/test_gatekeeper_api.py`.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.usefixtures("procesrecht_voor_de_beslisser")

TENANT = 7
OTHER_TENANT = 8

#: De mens die de agent de opdracht gaf. Hij mag het resultaat NIET zelf goedkeuren.
REQUESTER_ID = 42

#: Een tweede beheerder. Die mag het wel -- anders is "weiger alles" een geldige oplossing.
OTHER_ADMIN_ID = 43


def _user(user_id: int, tenant_id: int = TENANT) -> Any:
    """Een gebruikersobject zoals `get_current_user` het teruggeeft, met beheerdersrol."""
    from src.core.api.auth.schemas import UserResponse

    return UserResponse(
        id=user_id,
        email=f"beheerder{user_id}@klant.example",
        tenant_id=tenant_id,
        roles=["admin"],
    )


@pytest_asyncio.fixture
async def sessions() -> Any:
    """Een echte SQLAlchemy-sessiefabriek met alleen de `hitl_requests`-tabel.

    Geen mock: de kolomdefinities die deze test toetst zijn juist het onderwerp, dus ze moeten uit
    het echte model komen.
    """
    from src.core.governance.models import HITLRequestModel

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(HITLRequestModel.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _produce_ticket(
    factory: async_sessionmaker[AsyncSession],
    *,
    requested_by_user_id: int,
    tenant_id: int = TENANT,
) -> str:
    """Laat de ECHTE gatekeeper een ticket maken en persisteer het met de ECHTE repository.

    Geeft de ticketverwijzing terug. `title="access_pii"` valt in `HIGH_RISK_TASK_TYPES` en
    activeert daarmee de standaardregel POL-001 (`required_approvals=["manual_approval"]`), dus
    `evaluate_task` komt langs `_create_hitl_request`. Dat is de enige plek in de productiecode
    die een `HITLRequest` voor deze tabel opbouwt.
    """
    from src.core.als.enterprise.departments.department_orchestrator import Department
    from src.core.als.enterprise.gatekeeper import Gatekeeper
    from src.core.als.enterprise.gatekeeper_repository import GatekeeperRepository
    from src.core.shared.interfaces import TaskData

    gatekeeper = Gatekeeper(tenant_id=tenant_id)
    task = TaskData(
        title="access_pii",
        description="Haal het klantdossier op voor de kwartaalrapportage.",
        tenant_id=tenant_id,
    )
    record = await gatekeeper.evaluate_task(
        task,
        Department.HR,
        context={"user_id": requested_by_user_id},
    )
    assert record.hitl_ticket_ref is not None, (
        "De gatekeeper heeft geen HITL-ticket gemaakt voor een HIGH-risk PII-taak. Dan meet deze "
        "test niet wat hij denkt te meten -- controleer POL-001 in _init_default_policies."
    )

    produced = gatekeeper.get_hitl_requests_by_task(task.id)
    assert len(produced) == 1, f"Verwacht precies een HITLRequest, kreeg er {len(produced)}."

    async with factory() as session:
        await GatekeeperRepository(session, tenant_id).save_hitl_request(produced[0])

    return produced[0].ticket_ref


async def _produce_ticket_without_requester(
    factory: async_sessionmaker[AsyncSession],
    *,
    tenant_id: int = TENANT,
) -> str:
    """Zelfde echte producent, maar ZONDER `context` -- precies wat productie vandaag doet.

    `als/router.py::_check_gatekeeper` roept `evaluate_task(task)` aan met alleen de taak, en
    `TaskData` draagt geen menselijke aanvrager. Dit is dus geen bedacht randgeval maar het
    gedrag van de enige aanroeper die er is.
    """
    from src.core.als.enterprise.departments.department_orchestrator import Department
    from src.core.als.enterprise.gatekeeper import Gatekeeper
    from src.core.als.enterprise.gatekeeper_repository import GatekeeperRepository
    from src.core.shared.interfaces import TaskData

    gatekeeper = Gatekeeper(tenant_id=tenant_id)
    task = TaskData(
        title="access_pii",
        description="Autonome planner, geen menselijke opdrachtgever.",
        tenant_id=tenant_id,
    )
    await gatekeeper.evaluate_task(task, Department.HR)

    produced = gatekeeper.get_hitl_requests_by_task(task.id)
    assert len(produced) == 1
    assert produced[0].requested_by_user_id is None, (
        "De producent heeft toch een aanvrager gezet zonder dat er context was. Dan meet deze "
        "test niet het geval waarvoor hij bestaat."
    )

    async with factory() as session:
        await GatekeeperRepository(session, tenant_id).save_hitl_request(produced[0])

    return produced[0].ticket_ref


def _client(factory: async_sessionmaker[AsyncSession], user: Any, tenant_id: int) -> TestClient:
    """De echte route, de echte repository, en `user` als geauthenticeerde beheerder."""
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.dependencies import get_db
    from src.core.api.v1.gatekeeper import gatekeeper_hitl_router as module
    from src.core.auth.api_deps import get_current_user
    from src.core.middleware.tenant_context import set_tenant_id

    set_tenant_id(tenant_id)

    async def _db() -> Any:
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    # De CSRF-controle leunt op Redis en op een header die deze tests niet zetten. DAT hij bestaat
    # wordt bewezen door TestTheGatekeeperApprovalRoutesRequireACsrfToken in het buurbestand.
    app.dependency_overrides[validate_csrf_token] = lambda: None
    return TestClient(app)


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheRequesterIsRecorded:
    async def test_the_persisted_request_records_the_initiating_human(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """Zonder deze kolom kan geen enkele grens tussen aanvrager en goedkeurder bestaan.

        ASVS 8.3.3 vraagt om het OORSPRONKELIJKE subject. Dat moet dus de mens zijn die de agent
        de opdracht gaf, en die waarde moet de rit door de echte producent overleven.
        """
        from src.core.als.enterprise.gatekeeper_repository import GatekeeperRepository

        ticket_ref = await _produce_ticket(sessions, requested_by_user_id=REQUESTER_ID)

        async with sessions() as session:
            stored = await GatekeeperRepository(session, TENANT).get_hitl_by_ticket(ticket_ref)

        assert stored is not None, "De echte repository heeft de rij niet teruggevonden."
        assert stored.requested_by_user_id == REQUESTER_ID, (
            f"De opgeslagen aanvrager is {stored.requested_by_user_id!r} in plaats van "
            f"{REQUESTER_ID}. Zolang die identiteit onderweg wegvalt, kan de goedkeurroute niet "
            "vaststellen of de beslisser dezelfde mens is als de aanvrager (ADR-036 OP-81)."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheRequesterCannotApproveTheirOwnRequest:
    async def test_the_initiating_human_cannot_approve_their_own_request(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """De kern van OP-81: het vierogenprincipe uit ADR-015 op het geserveerde pad.

        De rolcheck uit OP-43 toetst een ROL, geen RELATIE. Een tenantbeheerder kon dus een agent
        namens zichzelf een HIGH-risk actie laten voorstellen en het resulterende ticket zelf
        goedkeuren -- bij de groep met de meeste rechten was het menselijk toezicht daarmee een
        formaliteit.
        """
        ticket_ref = await _produce_ticket(sessions, requested_by_user_id=REQUESTER_ID)
        client = _client(sessions, _user(REQUESTER_ID), TENANT)

        response = client.post(
            "/api/v1/gatekeeper/hitl/approve",
            json={"ticket_ref": ticket_ref, "approved_by": "wie dan ook"},
        )

        assert response.status_code == 403, (
            f"De aanvrager kreeg {response.status_code} op zijn EIGEN ticket. Dan is de HITL-poort "
            "uit ADR-015 zelf-goedkeurend en voldoet de goedkeuring niet aan ASVS 8.3.3."
        )

    async def test_the_initiating_human_cannot_reject_their_own_request(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """Afwijzen is net zo goed een governance-besluit -- zelfde grens, zelfde reden.

        Zonder deze helft kan de aanvrager zijn eigen aanvraag uit de wachtrij halen voordat een
        ander mens hem ziet, en verdwijnt het toezichtsspoor dat art. 14 juist eist.
        """
        ticket_ref = await _produce_ticket(sessions, requested_by_user_id=REQUESTER_ID)
        client = _client(sessions, _user(REQUESTER_ID), TENANT)

        response = client.post(
            "/api/v1/gatekeeper/hitl/reject",
            json={
                "ticket_ref": ticket_ref,
                "rejected_by": "wie dan ook",
                "reason": "Toch maar niet doen.",
            },
        )

        assert response.status_code == 403, (
            f"De aanvrager kreeg {response.status_code} bij het afwijzen van zijn EIGEN ticket."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestALegitimateApprovalStillWorks:
    """De andere richting van het mutatiebewijs.

    Zonder deze klasse is "weiger elke goedkeuring" een geldige oplossing voor de tests hierboven,
    en dan sloopt de guard de functionaliteit die hij hoort te beschermen.
    """

    async def test_another_administrator_can_still_approve_the_request(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        ticket_ref = await _produce_ticket(sessions, requested_by_user_id=REQUESTER_ID)
        client = _client(sessions, _user(OTHER_ADMIN_ID), TENANT)

        response = client.post(
            "/api/v1/gatekeeper/hitl/approve",
            json={"ticket_ref": ticket_ref, "approved_by": "wie dan ook"},
        )

        assert response.status_code == 200, (
            f"Een ANDERE beheerder kreeg {response.status_code} in plaats van 200 "
            f"({response.text}). De zelf-goedkeuringscheck mag alleen de aanvrager weigeren; "
            "weigert hij iedereen, dan is de HITL-wachtrij onbeoordeelbaar geworden."
        )

    async def test_another_administrator_can_still_reject_the_request(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        ticket_ref = await _produce_ticket(sessions, requested_by_user_id=REQUESTER_ID)
        client = _client(sessions, _user(OTHER_ADMIN_ID), TENANT)

        response = client.post(
            "/api/v1/gatekeeper/hitl/reject",
            json={
                "ticket_ref": ticket_ref,
                "rejected_by": "wie dan ook",
                "reason": "Buiten het mandaat van deze agent.",
            },
        )

        assert response.status_code == 200, (
            f"Een ANDERE beheerder kreeg {response.status_code} bij afwijzen ({response.text})."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTenantIsolation:
    """`save_hitl_request` schrijft de aanvrager; `get_hitl_by_ticket` moet tenant-gefilterd zijn.

    Backend-patterns par. 11: elke repository-methode filtert op `tenant_id` en krijgt een
    isolatietest. Hier bovendien met een reden die aan OP-81 zelf raakt: als tenant B het ticket
    van tenant A kan lezen, is `requested_by_user_id` een gebruikersnummer uit een andere tenant en
    vergelijkt de zelf-goedkeuringscheck twee getallen uit onvergelijkbare naamruimtes.
    """

    async def test_a_ticket_from_another_tenant_is_not_visible(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        from src.core.als.enterprise.gatekeeper_repository import GatekeeperRepository

        ticket_ref = await _produce_ticket(
            sessions, requested_by_user_id=REQUESTER_ID, tenant_id=TENANT
        )

        async with sessions() as session:
            leaked = await GatekeeperRepository(session, OTHER_TENANT).get_hitl_by_ticket(
                ticket_ref
            )

        assert leaked is None, (
            "Tenant B kreeg het HITL-ticket van tenant A te zien. Dat breekt ADR-005 en maakt de "
            "zelf-goedkeuringscheck betekenisloos: gebruikersnummers zijn per tenant."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestATicketWithoutATraceableRequester:
    """Fail-closed op goedkeuren, fail-open op afwijzen (ADR-036 OP-81, besluit Rakesh).

    **Waarom deze asymmetrie en niet symmetrisch fail-open.** Het broker-pad laat een ticket
    zonder bekende aanvrager gewoon goedkeuren, met als argument dat blokkeren de wachtrij zou
    vastzetten. Dat argument is hier gemeten en houdt geen stand: `save_hitl_request` heeft NUL
    aanroepers in `src/`, dus er zijn geen rijen om vast te laten lopen. En omdat AFWIJZEN open
    blijft, heeft elk ticket altijd een uitweg -- fail-secure zonder stilstand.

    Een goedkeuring is het art.-14-bewijs. Kan niemand vaststellen wie erom vroeg, dan is niet
    vast te stellen dat aanvrager en beslisser twee verschillende mensen zijn, en dan bewijst de
    goedkeuring niets. Afwijzen is de minst bevoorrechte uitkomst: het verleent geen enkel recht
    en laat de HIGH-risk actie juist NIET gebeuren.

    **Mutatiebewijs, beide richtingen (gemeten -- zie review-BE-SEC-049.md):**

    5. `_require_traceable_requester` uit `approve_hitl` verwijderd -> de approve-test hieronder
       wordt ROOD (het ticket is dan onbewijsbaar goed te keuren).
    6. `_require_traceable_requester` OOK aan `reject_hitl` toegevoegd -> de reject-test hieronder
       wordt ROOD (het ticket zou dan permanent onbeoordeelbaar zijn -- precies de vastgelopen
       wachtrij die deze asymmetrie voorkomt).
    """

    async def test_it_cannot_be_approved(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """Zonder herleidbare aanvrager is een goedkeuring geen bewijs, dus komt hij er niet."""
        ticket_ref = await _produce_ticket_without_requester(sessions)
        client = _client(sessions, _user(OTHER_ADMIN_ID), TENANT)

        response = client.post(
            "/api/v1/gatekeeper/hitl/approve",
            json={"ticket_ref": ticket_ref, "approved_by": "wie dan ook"},
        )

        assert response.status_code == 403, (
            f"Een ticket zonder herleidbare aanvrager werd goedgekeurd ({response.status_code}). "
            "Dan legt de goedkeuring niet vast dat aanvrager en beslisser twee verschillende "
            "mensen zijn, en dat is precies wat het art.-14-bewijs moet aantonen."
        )
        assert "REQUESTER_NOT_TRACEABLE" in response.text, (
            f"De weigering heeft niet de eigen foutcode maar: {response.text}. Een beheerder moet "
            "dit kunnen onderscheiden van een echte zelf-goedkeuring, want de vervolgactie is een "
            "andere."
        )

    async def test_it_can_still_be_rejected(
        self, sessions: async_sessionmaker[AsyncSession]
    ) -> None:
        """DIT is de uitweg. Zonder deze richting is fail-closed een vastgelopen wachtrij."""
        ticket_ref = await _produce_ticket_without_requester(sessions)
        client = _client(sessions, _user(OTHER_ADMIN_ID), TENANT)

        response = client.post(
            "/api/v1/gatekeeper/hitl/reject",
            json={
                "ticket_ref": ticket_ref,
                "rejected_by": "wie dan ook",
                "reason": "Geen herleidbare aanvrager, dus niet goed te keuren.",
            },
        )

        assert response.status_code == 200, (
            f"Afwijzen gaf {response.status_code} ({response.text}). Dan kan een ticket zonder "
            "herleidbare aanvrager de wachtrij niet verlaten: geen goedkeuring EN geen afwijzing "
            "is geen menselijk toezicht, alleen stilstand."
        )
