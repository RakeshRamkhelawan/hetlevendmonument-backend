"""
HITL Integration Tests

Tests for complete HITL flow end-to-end against real PostgreSQL database.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tool_broker.hitl_store import get_ticket_async
from src.core.tool_broker.hitl_repository import HITLTicketRepository


@pytest.fixture(autouse=True)
async def clear_hitl_store(db_session: AsyncSession):
    """Clear HITL store before each test."""
    await db_session.execute(text("DELETE FROM hitl_tickets;"))
    await db_session.commit()
    yield
    await db_session.execute(text("DELETE FROM hitl_tickets;"))
    await db_session.commit()


@pytest.fixture
def sample_ticket() -> Dict[str, Any]:
    """Create a sample HITL ticket."""
    return {
        "ticket_ref": "TOOL-TEST001",
        "agent_id": "test-agent-01",
        "tool_name": "test_tool",
        "tool_input": {"param": "value"},
        "reason": "Test reason for HITL",
        "task_id": "task-001",
        "status": "pending",
        "tenant_id": 1,
        "requested_by": "test@example.com",
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }


class TestHITLFlow:
    """End-to-end HITL flow tests."""

    @pytest.mark.asyncio
    async def test_complete_approval_flow(
        self, db_session: AsyncSession, sample_ticket: Dict[str, Any]
    ):
        """Test complete approval flow from creation to database persistence."""
        repo = HITLTicketRepository(db_session)
        payload = {
            **sample_ticket["tool_input"],
            "_agent_id": sample_ticket["agent_id"],
            "_reason": sample_ticket["reason"],
            "_task_id": sample_ticket["task_id"],
            "_requested_by": sample_ticket["requested_by"],
            "_requested_at": sample_ticket["requested_at"],
        }
        ticket = await repo.create(
            ticket_ref=sample_ticket["ticket_ref"],
            tenant_id=sample_ticket["tenant_id"],
            tool_name=sample_ticket["tool_name"],
            payload=payload,
            risk_level="HIGH",
        )
        await db_session.commit()

        # Verify ticket exists
        fetched = await get_ticket_async(sample_ticket["ticket_ref"], sample_ticket["tenant_id"], db_session)
        assert fetched is not None
        assert fetched["status"] == "pending"

        # Update ticket status (simulate approval)
        success = await repo.approve(
            ticket_ref=sample_ticket["ticket_ref"],
            tenant_id=sample_ticket["tenant_id"],
            user_id=1,  # seeded admin user
        )
        assert success is True
        await db_session.commit()

        # Verify updated status
        updated = await get_ticket_async(sample_ticket["ticket_ref"], sample_ticket["tenant_id"], db_session)
        assert updated["status"] == "approved"
        assert updated["approved_by"] == "admin@integration.test"

    @pytest.mark.asyncio
    async def test_complete_rejection_flow(
        self, db_session: AsyncSession, sample_ticket: Dict[str, Any]
    ):
        """Test complete rejection flow."""
        repo = HITLTicketRepository(db_session)
        payload = {
            **sample_ticket["tool_input"],
            "_agent_id": sample_ticket["agent_id"],
            "_reason": sample_ticket["reason"],
            "_task_id": sample_ticket["task_id"],
            "_requested_by": sample_ticket["requested_by"],
            "_requested_at": sample_ticket["requested_at"],
        }
        await repo.create(
            ticket_ref=sample_ticket["ticket_ref"],
            tenant_id=sample_ticket["tenant_id"],
            tool_name=sample_ticket["tool_name"],
            payload=payload,
            risk_level="HIGH",
        )
        await db_session.commit()

        # Reject
        success = await repo.reject(
            ticket_ref=sample_ticket["ticket_ref"],
            tenant_id=sample_ticket["tenant_id"],
            user_id=1,
        )
        assert success is True
        await db_session.commit()

        # Verify rejection
        updated = await get_ticket_async(sample_ticket["ticket_ref"], sample_ticket["tenant_id"], db_session)
        assert updated["status"] == "rejected"


class TestHITLTenantIsolation:
    """Tenant isolation tests for HITL."""

    @pytest.mark.asyncio
    async def test_tenant_cannot_access_other_tenant_tickets(self, db_session: AsyncSession):
        """Verify tenant isolation - tenant 1 cannot see tenant 2 tickets."""
        repo = HITLTicketRepository(db_session)

        # Create ticket for tenant 1
        await repo.create(
            ticket_ref="TOOL-T1-001",
            tenant_id=1,
            tool_name="tool",
            payload={"_agent_id": "a1", "_reason": "r1"},
            risk_level="HIGH",
        )

        # Create ticket for tenant 2
        await repo.create(
            ticket_ref="TOOL-T2-001",
            tenant_id=2,
            tool_name="tool",
            payload={"_agent_id": "a2", "_reason": "r2"},
            risk_level="HIGH",
        )
        await db_session.commit()

        # Verify tenant isolation in store
        from src.core.tool_broker.hitl_store import get_tickets_by_tenant_async

        t1_tickets = await get_tickets_by_tenant_async(1, db_session)
        t2_tickets = await get_tickets_by_tenant_async(2, db_session)

        t1_refs = [t["ticket_ref"] for t in t1_tickets]
        t2_refs = [t["ticket_ref"] for t in t2_tickets]

        assert len(t1_refs) == 1
        assert "TOOL-T1-001" in t1_refs
        assert "TOOL-T2-001" not in t1_refs

        assert len(t2_refs) == 1
        assert "TOOL-T2-001" in t2_refs
        assert "TOOL-T1-001" not in t2_refs


class TestHITLAPIEndpoints:
    """API endpoint integration tests."""

    @pytest.mark.asyncio
    async def test_hitl_endpoints_exist(self, client: AsyncClient):
        """Verify HITL endpoints are registered."""
        # Check endpoints are accessible (will return 401 without auth, but not 404)
        response = await client.get("/v1/tools/hitl/pending")
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

        response = await client.get("/v1/tools/hitl/audit")
        assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]

    @pytest.mark.asyncio
    async def test_hitl_request_validation(self, client: AsyncClient):
        """Test HITL request endpoint validation."""
        # Without auth should get 401
        response = await client.post(
            "/v1/tools/hitl/request",
            json={
                "agent_id": "test",
                "tool_name": "test_tool",
                "reason": "Test reason here",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_hitl_required_verdict_creates_db_ticket_and_rest_approve_visible_to_execute_tool(
    db_session: AsyncSession,
):
    """
    E2E flow:
    1. CopilotService ontvangt HITL_REQUIRED verdict
    2. HITLTicketRepository.create_hitl_request maakt DB-ticket aan
    3. REST-approve endpoint update status naar approved
    4. ToolBrokerService.execute_tool leest approved status en slaagt
    """
    from src.core.tool_broker.hitl_repository import HITLTicketRepository
    from src.core.tool_broker.hitl_store import HITLStore

    repo = HITLTicketRepository(db_session)
    ticket_ref = await repo.create_hitl_request(
        tenant_id=1,
        user_id=SEEDED_ADMIN_ID,
        decision_id="d-001",
        reason="High risk",
        action_type="delete_task",
        action_params={"key": "val"},
    )
    assert ticket_ref.startswith("hitl_")
    await db_session.commit()

    # Verifieer ticket bestaat in DB
    ticket = await repo.get(ticket_ref, tenant_id=1)
    assert ticket is not None
    assert ticket.status == "pending"

    # Approve
    updated = await repo.approve(ticket_ref, tenant_id=1, user_id=1)
    assert updated is True
    await db_session.commit()

    # ToolBrokerService leest approved status
    store = HITLStore(repo)
    status_val = await store.get_approval_status(ticket_ref, tenant_id=1)
    assert status_val == "approved"


PII_THAT_FITS_THE_SHAPE = "Jan_Jansen_salaris_82000"

#: `hitl_tickets.resolved_by` is een FK naar `users.id`. De geseede integratie-admin heeft
#: id 1 (`tests/integration/conftest.py:1102`); een verzonnen id geeft een
#: ForeignKeyViolationError en daarna is de hele transactie afgebroken -- dan falen ook de
#: opruimfixtures met 'current transaction is aborted'.
SEEDED_ADMIN_ID = 1


@pytest.mark.integration
class TestResolvingReallyRemovesTheContent:
    """Tegen ECHTE Postgres: doet de JSONB-expressie wat de SQL-tekst suggereert (ADR-036 OP-47)?

    De unit-tests in `tests/unit/test_hitl_repository.py` toetsen of `jsonb_build_object` en de
    bewaarde sleutels in de gecompileerde SQL-TEKST voorkomen. Dat is een vormtoets: een expressie
    die syntactisch klopt maar semantisch het verkeerde doet komt daar doorheen. De Taak 2-review
    wees daar expliciet op, en terecht -- deze klasse toetst het GEDRAG.

    Twee dingen die alleen hier bewijsbaar zijn: dat `jsonb_strip_nulls` geen NOT NULL-schending
    geeft wanneer alle bewaarde sleutels ontbreken (dan wordt het `{}`), en dat de PII er echt uit
    is in plaats van alleen niet-genoemd in de query.
    """

    @staticmethod
    async def _seed(db: AsyncSession, ticket_ref: str, *, extra: Dict[str, Any] | None = None) -> None:
        repo = HITLTicketRepository(db)
        payload: Dict[str, Any] = {
            "role": PII_THAT_FITS_THE_SHAPE,
            "_decision_id": "decision-42",
            "_agent_id": "agent-007",
            "_task_id": "task-99",
            "_requested_by": "user:7",
            "_requested_at": datetime.now(timezone.utc).isoformat(),
            "_reason": "Het model vond dit een goed idee omdat Jan Jansen erom vroeg.",
        }
        payload.update(extra or {})
        await repo.create(
            ticket_ref=ticket_ref,
            tenant_id=1,
            tool_name="local__run_shell",
            payload=payload,
            risk_level="HIGH",
        )
        await db.commit()

    @staticmethod
    async def _payload(db: AsyncSession, ticket_ref: str) -> Dict[str, Any]:
        row = await db.execute(
            text("SELECT payload FROM hitl_tickets WHERE ticket_ref = :ref"),
            {"ref": ticket_ref},
        )
        stored = row.scalar_one()
        return dict(stored or {})

    @pytest.mark.asyncio
    async def test_approving_removes_the_model_written_content(self, db_session: AsyncSession):
        await self._seed(db_session, "TOOL-INT-APPROVE")
        repo = HITLTicketRepository(db_session)

        assert await repo.approve("TOOL-INT-APPROVE", tenant_id=1, user_id=SEEDED_ADMIN_ID) is True
        await db_session.commit()

        payload = await self._payload(db_session, "TOOL-INT-APPROVE")
        rendered = str(payload)

        assert PII_THAT_FITS_THE_SHAPE not in rendered, (
            f"Het persoonsgegeven staat nog in de opgeslagen payload: {payload}. De "
            "JSONB-expressie compileert dus wel maar doet niet wat hij moet doen."
        )
        assert "role" not in payload, "de modelsleutel `role` staat er nog in"
        assert "_reason" not in payload, (
            "`_reason` is bewaard, maar dat is `explanation_for_user` en dus modeltekst"
        )

    @pytest.mark.asyncio
    async def test_approving_keeps_the_decision(self, db_session: AsyncSession):
        """De andere richting: wissen mag het besluit niet meenemen."""
        await self._seed(db_session, "TOOL-INT-KEEP")
        repo = HITLTicketRepository(db_session)

        await repo.approve("TOOL-INT-KEEP", tenant_id=1, user_id=SEEDED_ADMIN_ID)
        await db_session.commit()

        payload = await self._payload(db_session, "TOOL-INT-KEEP")

        for key in ("_decision_id", "_requested_by", "_requested_at"):
            assert key in payload, (
                f"`{key}` is weg. Dit zijn de drie sleutels die `create_hitl_request` zelf zet, NA "
                f"de spreiding van action_params -- samen zijn ze het besluit. Zonder die drie is "
                f"er na het opruimen niets meer dat zegt WIE wat wanneer besloot. "
                f"Gevonden: {sorted(payload)}"
            )

        # En de andere kant (ADR-036 OP-65). Deze test eiste eerder dat `_agent_id` en `_task_id`
        # OOK bewaard bleven, met als reden dat ze uit de request-body van de aanroeper zouden
        # komen. Dat geldt voor `/hitl/request` -- en die route is niet gemount. Op het live pad
        # zet `create_hitl_request` ze niet, dus wat daar onder die namen staat is rauwe
        # modeluitvoer. `agent_id` valt na een beslissing dus terug op "unknown" en `task_id` op
        # None, en dat is het juiste gedrag: een waarde die van het model kwam is geen
        # herkomstbewijs.
        for key in ("_agent_id", "_task_id"):
            assert key not in payload, (
                f"`{key}` overleeft de beslissing. Op het live pad schrijft niets die sleutel, dus "
                f"dit is door een taalmodel geschreven tekst die permanent bewaard blijft en wordt "
                f"getoond op /hitl/pending, /hitl/audit en over de tenantbrede websocket. "
                f"Gevonden: {sorted(payload)}"
            )

    @pytest.mark.asyncio
    async def test_rejecting_removes_the_content_too(self, db_session: AsyncSession):
        await self._seed(db_session, "TOOL-INT-REJECT")
        repo = HITLTicketRepository(db_session)

        assert await repo.reject("TOOL-INT-REJECT", tenant_id=1, user_id=SEEDED_ADMIN_ID) is True
        await db_session.commit()

        payload = await self._payload(db_session, "TOOL-INT-REJECT")
        assert PII_THAT_FITS_THE_SHAPE not in str(payload)

    @pytest.mark.asyncio
    async def test_a_pending_ticket_still_shows_everything(self, db_session: AsyncSession):
        """AI Act art. 14: wie goedkeurt moet zien wat hij goedkeurt.

        Zonder deze test is "wis altijd" een geldige oplossing, en dan keurt een mens iets goed
        zonder te weten wat er gebeurt.
        """
        await self._seed(db_session, "TOOL-INT-PENDING")

        payload = await self._payload(db_session, "TOOL-INT-PENDING")
        assert payload["role"] == PII_THAT_FITS_THE_SHAPE, (
            "Een nog niet beoordeeld ticket toont de waarden niet meer; dan is het menselijk "
            "toezicht een formaliteit."
        )

    @pytest.mark.asyncio
    async def test_a_payload_without_any_kept_key_does_not_violate_not_null(
        self, db_session: AsyncSession
    ):
        """`payload` is JSONB NOT NULL. `jsonb_strip_nulls` moet `{}` opleveren, geen NULL.

        Dit is het geval van `critique_store.py`, dat tickets schrijft waarvan GEEN ENKELE sleutel
        met een underscore begint. Als de expressie daar NULL zou opleveren, faalt de UPDATE met een
        integriteitsfout en blijft het ticket voor altijd pending.
        """
        repo = HITLTicketRepository(db_session)
        await repo.create(
            ticket_ref="TOOL-INT-NOMETA",
            tenant_id=1,
            tool_name="critic_agent",
            payload={"agent_name": "criticus", "score": 0.2},
            risk_level="HIGH",
        )
        await db_session.commit()

        assert await repo.approve("TOOL-INT-NOMETA", tenant_id=1, user_id=SEEDED_ADMIN_ID) is True
        await db_session.commit()

        payload = await self._payload(db_session, "TOOL-INT-NOMETA")
        assert payload == {} or "_redacted_payload" in payload, (
            f"Onverwachte payload na het opruimen: {payload}"
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestAnApprovalIsSingleUseAgainstRealPostgres:
    """De begrenzing van OP-63, bewezen op een echte database.

    De unit-tests bewaken de VORM van de UPDATE (welke voorwaarden staan in de WHERE). Dat een
    tweede poging daadwerkelijk nul rijen raakt, en dat een andere tool of andere parameters
    daadwerkelijk niet passen, kan alleen de database zelf aantonen -- daar zit de vergelijking op
    `payload ->> '_approval_binding'`.
    """

    TOOL = "local__run_shell"
    APPROVED_COMMAND = "cleanup-build-artifacts --dry-run"
    OTHER_COMMAND = "deploy-to-production --force"

    @staticmethod
    async def _seed(db: AsyncSession, ticket_ref: str, params: Dict[str, Any]) -> None:
        repo = HITLTicketRepository(db)
        payload: Dict[str, Any] = dict(params)
        payload.update(
            {
                "_decision_id": "decision-1",
                "_requested_by": "user:7",
                "_requested_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        await repo.create(
            ticket_ref=ticket_ref,
            tenant_id=1,
            tool_name=TestAnApprovalIsSingleUseAgainstRealPostgres.TOOL,
            payload=payload,
            risk_level="HIGH",
        )
        await db.commit()

    async def _approve(self, db: AsyncSession, ticket_ref: str, params: Dict[str, Any]) -> None:
        from src.core.tool_broker.redaction import approval_binding

        repo = HITLTicketRepository(db)
        assert await repo.approve(
            ticket_ref,
            tenant_id=1,
            user_id=SEEDED_ADMIN_ID,
            binding=approval_binding(self.TOOL, params, tenant_id=1),
            note="akkoord, besproken met de teamlead",
        )
        await db.commit()

    async def test_the_same_approval_cannot_be_redeemed_twice(self, db_session: AsyncSession):
        params = {"command": self.APPROVED_COMMAND}
        await self._seed(db_session, "TOOL-INT-ONCE", params)
        await self._approve(db_session, "TOOL-INT-ONCE", params)
        repo = HITLTicketRepository(db_session)

        first = await repo.redeem(
            "TOOL-INT-ONCE", tenant_id=1, tool_name=self.TOOL, payload=params
        )
        await db_session.commit()
        second = await repo.redeem(
            "TOOL-INT-ONCE", tenant_id=1, tool_name=self.TOOL, payload=params
        )
        await db_session.commit()

        assert first is True, "De eerste verzilvering hoort te slagen."
        assert second is False, (
            "Dezelfde goedkeuring is twee keer te verzilveren. Een menselijke goedkeuring is een "
            "eenmalige handeling; blijft het ticket bruikbaar, dan is het een permanente volmacht."
        )

    async def test_an_old_approval_is_no_longer_redeemable(self, db_session: AsyncSession):
        """Een goedkeuring veroudert (ADR-036 OP-83).

        `approve` eiste al dat het ticket niet verlopen was, maar `redeem` kende geen tijdsgrens.
        Een actie die maanden geleden is goedgekeurd bleef uitvoerbaar. Menselijk toezicht gaat over
        een beslissing op een MOMENT, met de context van dat moment.
        """
        from datetime import timedelta

        from sqlalchemy import update as sa_update

        from src.core.tool_broker.models import HITLTicket

        params = {"command": self.APPROVED_COMMAND}
        await self._seed(db_session, "TOOL-INT-OUD", params)
        await self._approve(db_session, "TOOL-INT-OUD", params)

        # De goedkeuring naar het verleden schuiven; verder verandert er niets.
        await db_session.execute(
            sa_update(HITLTicket)
            .where(HITLTicket.ticket_ref == "TOOL-INT-OUD")
            .values(resolved_at=datetime.now(timezone.utc) - timedelta(days=30))
        )
        await db_session.commit()

        redeemed = await HITLTicketRepository(db_session).redeem(
            "TOOL-INT-OUD",
            tenant_id=1,
            tool_name=self.TOOL,
            payload={**params, "_hitl_ticket_ref": "TOOL-INT-OUD"},
        )

        assert redeemed is False, (
            "Een goedkeuring van dertig dagen geleden is nog steeds te verzilveren. Dan is de "
            "menselijke beoordeling losgekoppeld van het moment waarop hij gold."
        )

    async def test_an_approval_does_not_cover_another_tool(self, db_session: AsyncSession):
        params = {"command": self.APPROVED_COMMAND}
        await self._seed(db_session, "TOOL-INT-OTHERTOOL", params)
        await self._approve(db_session, "TOOL-INT-OTHERTOOL", params)

        allowed = await HITLTicketRepository(db_session).redeem(
            "TOOL-INT-OTHERTOOL", tenant_id=1, tool_name="local__send_email", payload=params
        )

        assert allowed is False, (
            "Een goedkeuring voor local__run_shell verzilvert ook voor local__send_email. "
            "Onbekende tools zijn bovendien standaard HIGH, dus dit geldt voor alles."
        )

    async def test_an_approval_does_not_cover_other_parameters(self, db_session: AsyncSession):
        params = {"command": self.APPROVED_COMMAND}
        await self._seed(db_session, "TOOL-INT-OTHERPARAMS", params)
        await self._approve(db_session, "TOOL-INT-OTHERPARAMS", params)

        allowed = await HITLTicketRepository(db_session).redeem(
            "TOOL-INT-OTHERPARAMS",
            tenant_id=1,
            tool_name=self.TOOL,
            payload={"command": self.OTHER_COMMAND},
        )

        assert allowed is False, (
            "Goedkeuren van een commando dekt ook een ANDER commando met dezelfde tool. De "
            "goedkeuring is dan niet aan de parameters gebonden."
        )

    async def test_the_human_reason_survives_in_the_database(self, db_session: AsyncSession):
        """OP-69: de motivering van de mens werd gevalideerd en weggegooid."""
        params = {"command": self.APPROVED_COMMAND}
        await self._seed(db_session, "TOOL-INT-NOTE", params)
        await self._approve(db_session, "TOOL-INT-NOTE", params)

        ticket = await HITLTicketRepository(db_session).get("TOOL-INT-NOTE", tenant_id=1)

        assert ticket is not None
        assert ticket.resolution_note == "akkoord, besproken met de teamlead", (
            "Wat de mens erbij schreef is niet bewaard. Op een endpoint waarvan de hele "
            "rechtvaardiging aantoonbaar menselijk toezicht is, was dat het enige dat verdween."
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestTheFullRoundTripFromCreationToRedemption:
    """De rondgang die alles hiervoor miste (ADR-036 OP-75).

    Elke test tot nu toe bouwde zijn eigen payload aan BEIDE kanten van de binding. Zo'n test
    toetst alleen dat de functie deterministisch is -- niet dat de twee kanten in productie
    hetzelfde zien. De blinde code-review van 2026-08-06 bouwde wel de echte rondgang en vond dat
    `redeem` altijd `False` gaf: `service.py` schrijft `tenant_id` en `user_id` uit de context in
    de payload voordat de poort draait, en die telden bij uitvoering wel mee in de binding en bij
    goedkeuring niet.

    Deze test loopt daarom over de ECHTE producent (`create_hitl_request`, het pad dat
    `copilot/service.py` gebruikt) en simuleert de contextinjectie zoals `execute_tool` hem doet.
    """

    # `delete_task` en niet `local__run_shell`: sinds ADR-036 OP-90 weigert `create_hitl_request`
    # een ticket voor een tool die de uitvoerende identiteit niet mag draaien, en `copilot` mag
    # geen shell. Gemeten met `ToolPermissionManager`. `delete_task` is wel toegestaan EN HIGH, dus
    # deze rondgang loopt door dezelfde poort als in productie.
    TOOL = "delete_task"
    PARAMS = {"task_id": "b7f1c2d4-0000-4000-8000-000000000001"}

    async def test_a_ticket_created_by_the_live_producer_can_be_redeemed(
        self, db_session: AsyncSession
    ):
        from src.core.tool_broker.redaction import approval_binding

        repo = HITLTicketRepository(db_session)

        # 1. Aangemaakt zoals de copilot het doet: action_params + servermetadata.
        ticket_ref = await repo.create_hitl_request(
            tenant_id=1,
            user_id=SEEDED_ADMIN_ID,
            decision_id="decision-round-trip",
            reason="Het model wil dit uitvoeren.",
            action_type=self.TOOL,
            action_params=dict(self.PARAMS),
        )
        await db_session.commit()

        # 2. Goedgekeurd zoals de router het doet: binding over de payload van het ticket.
        ticket = await repo.get(ticket_ref, tenant_id=1)
        assert ticket is not None
        assert await repo.approve(
            ticket_ref,
            tenant_id=1,
            user_id=SEEDED_ADMIN_ID,
            binding=approval_binding(ticket.tool_name, ticket.payload, tenant_id=1),
            note="akkoord",
        )
        await db_session.commit()

        # 3. Uitgevoerd zoals `execute_tool` het doet: de aanroeper geeft de ticketverwijzing mee
        #    en de broker injecteert tenant_id en user_id uit de EXECUTIECONTEXT.
        payload_bij_uitvoering = {
            **self.PARAMS,
            "_hitl_ticket_ref": ticket_ref,
            "tenant_id": 1,
            "user_id": SEEDED_ADMIN_ID,
        }
        redeemed = await repo.redeem(
            ticket_ref, tenant_id=1, tool_name=self.TOOL, payload=payload_bij_uitvoering
        )

        assert redeemed is True, (
            "Een ticket dat door de ECHTE producent is gemaakt en netjes is goedgekeurd, kan niet "
            "worden verzilverd. De goedgekeurde actie blijft dan permanent geblokkeerd -- precies "
            "wat OP-37 zou oplossen, maar dan een laag dieper en zonder foutmelding."
        )

    async def test_the_round_trip_still_refuses_other_parameters(
        self, db_session: AsyncSession
    ):
        """Vangnet op de rondgang: de fix mag de begrenzing niet weggooien."""
        from src.core.tool_broker.redaction import approval_binding

        repo = HITLTicketRepository(db_session)
        ticket_ref = await repo.create_hitl_request(
            tenant_id=1,
            user_id=SEEDED_ADMIN_ID,
            decision_id="decision-round-trip-2",
            reason="Het model wil dit uitvoeren.",
            action_type=self.TOOL,
            action_params=dict(self.PARAMS),
        )
        await db_session.commit()
        ticket = await repo.get(ticket_ref, tenant_id=1)
        assert ticket is not None
        await repo.approve(
            ticket_ref,
            tenant_id=1,
            user_id=SEEDED_ADMIN_ID,
            binding=approval_binding(ticket.tool_name, ticket.payload, tenant_id=1),
        )
        await db_session.commit()

        redeemed = await repo.redeem(
            ticket_ref,
            tenant_id=1,
            tool_name=self.TOOL,
            payload={
                "command": "deploy-to-production --force",
                "_hitl_ticket_ref": ticket_ref,
                "tenant_id": 1,
                "user_id": SEEDED_ADMIN_ID,
            },
        )

        assert redeemed is False, (
            "Na de fix dekt een goedkeuring ook een ANDER commando. Dan is de binding zinloos."
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestTheNewRepositoryMethodsIsolateTenants:
    """Elke nieuwe repository-methode vereist een isolatietest (backend-patterns par. 11).

    Die ontbraken voor `redeem` en `count_by_tenant`, en de blinde code-review toonde het gevolg:
    het `tenant_id`-filter uit de WHERE halen liet respectievelijk 284 en 289 tests groen. De
    unit-tests konden het niet zien omdat de nep-repository zijn EIGEN tenantcontrole doet -- het
    namaakobject was strenger dan de productiecode. De integratietests gebruikten alleen tenant 1.
    """

    TOOL = "local__run_shell"
    PARAMS = {"command": "cleanup-build-artifacts --dry-run"}

    async def _approved_ticket_for(self, db: AsyncSession, tenant_id: int, ref_suffix: str) -> str:
        from src.core.tool_broker.redaction import approval_binding

        repo = HITLTicketRepository(db)
        ticket_ref = f"TOOL-ISO-{ref_suffix}"
        await repo.create(
            ticket_ref=ticket_ref,
            tenant_id=tenant_id,
            tool_name=self.TOOL,
            payload=dict(self.PARAMS),
            risk_level="HIGH",
        )
        await db.commit()
        ticket = await repo.get(ticket_ref, tenant_id=tenant_id)
        assert ticket is not None
        await repo.approve(
            ticket_ref,
            tenant_id=tenant_id,
            user_id=SEEDED_ADMIN_ID,
            binding=approval_binding(self.TOOL, ticket.payload, tenant_id=tenant_id),
        )
        await db.commit()
        return ticket_ref

    async def test_redeem_refuses_a_ticket_of_another_tenant(self, db_session: AsyncSession):
        ticket_ref = await self._approved_ticket_for(db_session, tenant_id=1, ref_suffix="REDEEM")

        redeemed = await HITLTicketRepository(db_session).redeem(
            ticket_ref,
            tenant_id=2,
            tool_name=self.TOOL,
            payload={**self.PARAMS, "_hitl_ticket_ref": ticket_ref},
        )

        assert redeemed is False, (
            "Tenant 2 verzilvert een goedkeuring van tenant 1. De ticketverwijzing is raadbaar noch "
            "geheim -- hij staat in API-antwoorden -- dus dit is een volwaardige tenantdoorbraak op "
            "het pad dat juist HIGH-risk acties bewaakt."
        )
        # WAT DEZE TEST WEL EN NIET AANTOONT. Hij bewijst de EIGENSCHAP (tenant 2 komt er niet in),
        # maar niet WELKE laag hem tegenhoudt: de tenant zit ook in de domeinscheiding van de HMAC,
        # dus de binding matcht al niet. Gemeten: het `tenant_id`-filter uit de WHERE van `redeem`
        # halen laat deze test GROEN. Dat filter is dus verdediging-in-de-diepte, geen enige grens.
        # Dat het er STAAT wordt daarom apart bewaakt in
        # `tests/unit/tool_broker/test_hitl_approval_is_bounded.py::TestTheTenantFilterIsPresent`.

    async def test_redeem_still_works_for_the_owning_tenant(self, db_session: AsyncSession):
        """Vangnet: altijd weigeren zou de test hierboven ook groen maken."""
        ticket_ref = await self._approved_ticket_for(db_session, tenant_id=1, ref_suffix="REDEEMOK")

        redeemed = await HITLTicketRepository(db_session).redeem(
            ticket_ref,
            tenant_id=1,
            tool_name=self.TOOL,
            payload={**self.PARAMS, "_hitl_ticket_ref": ticket_ref},
        )

        assert redeemed is True

    async def test_get_refuses_a_ticket_of_another_tenant(self, db_session: AsyncSession):
        """Gedrag naast de vorm: tenant A ziet een ticket van tenant B niet.

        Dit is het filter waar approve en reject op leunen. In tegenstelling tot `redeem` is er
        hier GEEN tweede laag (de binding zit daar niet in), dus dit filter is de enige grens.
        """
        repo = HITLTicketRepository(db_session)
        await repo.create(
            ticket_ref="TOOL-ISO-GET",
            tenant_id=1,
            tool_name=self.TOOL,
            payload=dict(self.PARAMS),
            risk_level="HIGH",
        )
        await db_session.commit()

        van_andere_tenant = await repo.get("TOOL-ISO-GET", tenant_id=2)

        assert van_andere_tenant is None, (
            "Tenant 2 krijgt een ticket van tenant 1 te zien. approve en reject concluderen uit "
            "een treffer dat het ticket van jou is, dus dit is meteen goedkeuren namens een andere "
            "organisatie."
        )

    async def test_get_still_returns_the_ticket_to_its_owner(self, db_session: AsyncSession):
        """Vangnet: altijd None teruggeven zou de test hierboven ook groen maken."""
        repo = HITLTicketRepository(db_session)
        await repo.create(
            ticket_ref="TOOL-ISO-GETOK",
            tenant_id=1,
            tool_name=self.TOOL,
            payload=dict(self.PARAMS),
            risk_level="HIGH",
        )
        await db_session.commit()

        eigen = await repo.get("TOOL-ISO-GETOK", tenant_id=1)

        assert eigen is not None

    async def test_count_by_tenant_does_not_count_another_tenant(self, db_session: AsyncSession):
        repo = HITLTicketRepository(db_session)
        for tenant_id, suffix in ((1, "CNT-A"), (2, "CNT-B"), (2, "CNT-C")):
            await repo.create(
                ticket_ref=f"TOOL-{suffix}",
                tenant_id=tenant_id,
                tool_name=self.TOOL,
                payload=dict(self.PARAMS),
                risk_level="HIGH",
            )
        await db_session.commit()

        van_tenant_twee = await repo.count_by_tenant(tenant_id=2)

        assert van_tenant_twee == 2, (
            f"`count_by_tenant` telt {van_tenant_twee} in plaats van 2. Zonder tenantfilter is het "
            "aantal op /hitl/pending en /hitl/audit dat van ALLE tenants -- dat lekt hoeveel "
            "HIGH-risk acties een andere organisatie uitvoert."
        )

    async def test_get_by_tenant_filters_on_status(self, db_session: AsyncSession):
        """Het statusfilter had geen gedragsdekking (blinde review, MEDIUM).

        Het filter weghalen liet 507 tests groen. Gevolg: `/hitl/pending` zou ook goedgekeurde,
        afgewezen en verbruikte tickets tonen -- en dat is juist het oppervlak dat bewust het
        ONBEWERKTE `tool_input` laat zien.
        """
        repo = HITLTicketRepository(db_session)
        await repo.create(
            ticket_ref="TOOL-STATUS-PENDING",
            tenant_id=3,
            tool_name=self.TOOL,
            payload=dict(self.PARAMS),
            risk_level="HIGH",
        )
        await repo.create(
            ticket_ref="TOOL-STATUS-DONE",
            tenant_id=3,
            tool_name=self.TOOL,
            payload=dict(self.PARAMS),
            risk_level="HIGH",
        )
        await db_session.commit()
        await repo.approve("TOOL-STATUS-DONE", tenant_id=3, user_id=SEEDED_ADMIN_ID)
        await db_session.commit()

        openstaand = await repo.get_by_tenant(tenant_id=3, status="pending")

        refs = sorted(t.ticket_ref for t in openstaand)
        assert refs == ["TOOL-STATUS-PENDING"], (
            f"`get_by_tenant(status='pending')` geeft {refs}. Zonder werkend statusfilter toont "
            "/hitl/pending ook al afgehandelde tickets, inclusief hun onbewerkte tool_input."
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestAFailingAuditWriteDoesNotUnconsumeTheApproval:
    """Een verbruikte goedkeuring blijft verbruikt (ADR-036 OP-100).

    **Hoe dit gevonden is.** De blinde securityreview van 2026-08-08, aangetoond tegen een echte
    database. De volgorde in `approve_hitl_request` was: goedkeuring vastleggen (commit) -> uitvoeren
    (de poort verzilvert het ticket in DEZELFDE sessie, nog niet vastgelegd) -> de ADR-019-regel
    schrijven binnen `best_effort`.

    `best_effort` rolt de sessie terug bij een fout -- dat is zijn hele doel, want een auditregel
    mag de primaire handeling nooit blokkeren. Maar daarmee rolde hij ook de verzilvering terug. Het
    ticket sprong terug op `approved`, er was GEEN auditregel, en de goedkeuring was binnen het
    venster van 24 uur opnieuw te verzilveren -- door de oorspronkelijke aanvrager, die de
    ticketverwijzing in zijn eigen antwoord terugkrijgt.

    De eenmaligheid uit OP-63/OP-75 hing dus aan iets dat per definitie mag falen.
    """

    TOOL = "delete_task"
    PARAMS = {"task_id": "c8e2d3f5-0000-4000-8000-000000000002"}

    async def test_without_a_commit_the_rollback_undoes_the_consumption(
        self, db_session: AsyncSession
    ):
        from src.core.tool_broker.redaction import approval_binding

        repo = HITLTicketRepository(db_session)
        ticket_ref = await repo.create_hitl_request(
            tenant_id=1,
            user_id=SEEDED_ADMIN_ID,
            decision_id="decision-audit-faalt",
            reason="Het model wil dit uitvoeren.",
            action_type=self.TOOL,
            action_params=dict(self.PARAMS),
        )
        await db_session.commit()

        ticket = await repo.get(ticket_ref, tenant_id=1)
        assert ticket is not None
        await repo.approve(
            ticket_ref,
            tenant_id=1,
            user_id=SEEDED_ADMIN_ID,
            binding=approval_binding(self.TOOL, ticket.payload, tenant_id=1),
        )
        await db_session.commit()

        # Verzilveren zoals de poort het doet, en daarna een MISLUKTE auditregel simuleren: dat is
        # exact de situatie die de review aantoonde.
        assert await repo.redeem(
            ticket_ref,
            tenant_id=1,
            tool_name=self.TOOL,
            payload={**self.PARAMS, "_hitl_ticket_ref": ticket_ref},
        )

        # DIT is het mechanisme, en daarom staat de commit in de router VOOR de auditregel:
        # zonder die commit rolt `best_effort` de verzilvering mee terug.
        from src.core.utils.best_effort import best_effort

        async with best_effort("ADR-019 auditregel", db_session=db_session):
            raise RuntimeError("de auditregel faalt")

        opnieuw = await repo.redeem(
            ticket_ref,
            tenant_id=1,
            tool_name=self.TOOL,
            payload={**self.PARAMS, "_hitl_ticket_ref": ticket_ref},
        )

        assert opnieuw is True, (
            "De verzilvering overleeft een teruggerolde sessie ook ZONDER commit. Dan klopt de "
            "aanname onder OP-100 niet meer en is de commit in de router mogelijk overbodig -- "
            "controleer of `best_effort` nog terugrolt voordat je die weghaalt."
        )

    async def test_committing_first_makes_the_consumption_survive(
        self, db_session: AsyncSession
    ):
        """Dezelfde reeks MET de commit ertussen -- zo doet de router het sinds OP-100.

        Deze test bewijst het mechanisme, niet de vololgorde in de router. Dat laatste wordt
        afgedwongen door `tests/unit/api/test_approve_commits_before_the_audit_entry.py`, want een
        test die zelf commit kan niet zien of de PRODUCTIECODE dat ook doet.
        """
        from src.core.tool_broker.redaction import approval_binding
        from src.core.utils.best_effort import best_effort

        repo = HITLTicketRepository(db_session)
        ticket_ref = await repo.create_hitl_request(
            tenant_id=1,
            user_id=SEEDED_ADMIN_ID,
            decision_id="decision-audit-faalt-2",
            reason="Het model wil dit uitvoeren.",
            action_type=self.TOOL,
            action_params=dict(self.PARAMS),
        )
        await db_session.commit()
        ticket = await repo.get(ticket_ref, tenant_id=1)
        assert ticket is not None
        await repo.approve(
            ticket_ref,
            tenant_id=1,
            user_id=SEEDED_ADMIN_ID,
            binding=approval_binding(self.TOOL, ticket.payload, tenant_id=1),
        )
        await db_session.commit()

        assert await repo.redeem(
            ticket_ref,
            tenant_id=1,
            tool_name=self.TOOL,
            payload={**self.PARAMS, "_hitl_ticket_ref": ticket_ref},
        )
        await db_session.commit()

        async with best_effort("ADR-019 auditregel", db_session=db_session):
            raise RuntimeError("de auditregel faalt")

        opnieuw = await repo.redeem(
            ticket_ref,
            tenant_id=1,
            tool_name=self.TOOL,
            payload={**self.PARAMS, "_hitl_ticket_ref": ticket_ref},
        )

        assert opnieuw is False, (
            "Zelfs met de commit ertussen is de goedkeuring opnieuw te verzilveren. Dan zit het "
            "probleem dieper dan de transactiegrens."
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestTheRedemptionIsDurableBeforeTheSideEffect:
    """De verzilvering ligt vast VOOR de tool draait (ADR-036 H-1, 2026-08-09).

    **De bevinding.** `redeem` zet `approved` -> `consumed` op de request-sessie. Tussen die
    UPDATE en de eerstvolgende commit draait de tool -- tot 30 seconden lang. Wordt het verzoek
    in dat venster afgebroken (werker-recycling per ADR-011, een client die wegklikt, SIGTERM
    tijdens een deploy), dan loopt `get_db` zijn `except Exception` NIET: `CancelledError` erft
    van `BaseException`. De transactie wordt weggegooid. Uitkomst: de tool IS uitgevoerd, het
    ticket staat weer op `approved`, en de goedkeuring is binnen 24 uur opnieuw te verzilveren
    door de aanvrager -- die de ticketverwijzing in zijn eigen antwoord terugkrijgt.

    **Waarom deze test over `execute_tool` loopt en niet over `repo.redeem`.** De twee tests
    hierboven (OP-100) sturen de repository rechtstreeks aan. Die bewijzen het MECHANISME, maar
    niet dat de productiecode het ook zo doet -- een test die zelf commit kan niet zien of
    `execute_tool` dat ook doet. Deze test roept daarom de ECHTE poort aan, via de ECHTE
    bedrading (`ToolBrokerDependencies.get_service(db=...)`).

    **Wat deze test WEL en NIET bewijst.** Wel: de verzilvering is vrijgegeven voordat het
    neveneffect begint, dus een teruggerolde request-transactie maakt haar niet ongedaan. Niet:
    bestand tegen procesdood -- de integratie-opstelling draait alles in een buitenste
    transactie die aan het eind altijd terugrolt (`join_transaction_mode="create_savepoint"`),
    dus een commit hier is een savepoint-release. Dat is precies genoeg om de vraag te
    beantwoorden die ertoe doet: gebeurt het VOOR of NA de tool.

    **Mutatietest (2026-08-09):** de commit in `service.py` (in de HITL-poort, na een geslaagde
    `redeem_approval`) weggehaald -> ROOD. Terug -> GROEN.
    """

    TOOL = "delete_task"
    PARAMS = {"task_id": "c8e2d3f5-0000-4000-8000-000000000003"}

    async def test_an_aborted_request_leaves_the_redemption_standing(
        self, db_session: AsyncSession
    ):
        from src.core.tool_broker.dependencies import ToolBrokerDependencies
        from src.core.tool_broker.redaction import approval_binding

        repo = HITLTicketRepository(db_session)
        ticket_ref = await repo.create_hitl_request(
            tenant_id=1,
            user_id=SEEDED_ADMIN_ID,
            decision_id="decision-h1-afgebroken",
            reason="Het model wil dit uitvoeren.",
            action_type=self.TOOL,
            action_params=dict(self.PARAMS),
        )
        await db_session.commit()

        ticket = await repo.get(ticket_ref, tenant_id=1)
        assert ticket is not None
        await repo.approve(
            ticket_ref,
            tenant_id=1,
            user_id=SEEDED_ADMIN_ID,
            binding=approval_binding(self.TOOL, ticket.payload, tenant_id=1),
        )
        await db_session.commit()

        # De ECHTE poort, via de ECHTE bedrading. Of de tool zelf slaagt doet er niet toe --
        # de vraag is of de VERZILVERING vastligt op het moment dat het neveneffect begint.
        broker = ToolBrokerDependencies.get_service(db=db_session)
        try:
            await broker.execute_tool(
                tool_name=self.TOOL,
                payload={**self.PARAMS, "_hitl_ticket_ref": ticket_ref},
                agent_id="copilot",
                context={"tenant_id": 1, "user_id": SEEDED_ADMIN_ID},
            )
        except Exception:  # noqa: BLE001 -- de uitkomst van de tool is hier niet de vraag
            pass

        verzilverd = await repo.get(ticket_ref, tenant_id=1)
        assert verzilverd is not None and verzilverd.status == "consumed", (
            f"De poort heeft het ticket niet verzilverd (status {verzilverd.status!r} als het "
            "bestaat). Dan meet de rest van deze test niets -- eerst uitzoeken waarom de "
            "verzilvering niet gebeurde."
        )

        # HET AFGEBROKEN VERZOEK: de request-transactie wordt weggegooid zonder commit.
        await db_session.rollback()

        na_afbreken = await repo.get(ticket_ref, tenant_id=1)
        assert na_afbreken is not None and na_afbreken.status == "consumed", (
            f"Na een afgebroken verzoek staat het ticket op {na_afbreken.status if na_afbreken else None!r} "
            "in plaats van 'consumed'. De tool is dan wel uitgevoerd maar de goedkeuring is "
            "weer bruikbaar: dezelfde HIGH-risk actie kan binnen 24 uur nog een keer draaien, "
            "en er is geen auditregel van de uitvoering die wel gebeurde (ADR-036 H-1)."
        )
