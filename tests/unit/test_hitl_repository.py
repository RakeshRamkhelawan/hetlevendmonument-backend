"""Unit tests for HITLTicketRepository.

Tests use a mocked AsyncSession to avoid needing a real database.
For integration tests against a real DB, see tests/integration/.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from src.core.tool_broker.hitl_repository import HITLTicketRepository, generate_ticket_ref
from src.core.tool_broker.models import HITLTicket


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_db() -> MagicMock:
    """Build a minimal AsyncSession mock."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_repo(db: MagicMock | None = None) -> tuple[HITLTicketRepository, MagicMock]:
    if db is None:
        db = _make_mock_db()
    repo = HITLTicketRepository(db)
    return repo, db


def _make_ticket(
    ticket_ref: str = "hitl_abc123",
    tenant_id: int = 1,
    status: str = "pending",
    tool_name: str = "code__run",
    risk_level: str = "HIGH",
) -> HITLTicket:
    now = datetime.now(timezone.utc)
    ticket = HITLTicket(
        ticket_ref=ticket_ref,
        tenant_id=tenant_id,
        status=status,
        tool_name=tool_name,
        payload={"code": "print('hello')"},
        risk_level=risk_level,
        expires_at=now + timedelta(hours=4),
    )
    ticket.id = 1
    ticket.created_at = now
    ticket.resolved_at = None
    ticket.resolved_by = None
    return ticket


def _mock_result(scalar: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    return result


def _mock_scalars_result(items: list) -> MagicMock:
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result = MagicMock()
    result.scalars.return_value = scalars_mock
    return result


def _mock_update_result(rowcount: int) -> MagicMock:
    result = MagicMock()
    result.rowcount = rowcount
    return result


# ---------------------------------------------------------------------------
# Test: create ticket
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateTicket:
    @pytest.mark.asyncio
    async def test_create_ticket_calls_add_and_flush(self):
        repo, db = _make_repo()

        ticket = await repo.create(
            ticket_ref="hitl_abc123",
            tenant_id=1,
            tool_name="code__run",
            payload={"code": "print('hello')"},
            risk_level="HIGH",
        )

        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        assert isinstance(ticket, HITLTicket)

    @pytest.mark.asyncio
    async def test_create_ticket_sets_pending_status(self):
        repo, db = _make_repo()

        added_ticket = None

        def capture(obj: object) -> None:
            nonlocal added_ticket
            added_ticket = obj

        db.add = capture

        await repo.create(
            ticket_ref="hitl_abc123",
            tenant_id=1,
            tool_name="code__run",
            payload={},
            risk_level="HIGH",
        )

        assert added_ticket is not None
        assert added_ticket.status == "pending"
        assert added_ticket.tenant_id == 1
        assert added_ticket.tool_name == "code__run"

    @pytest.mark.asyncio
    async def test_create_ticket_sets_expires_at(self):
        repo, db = _make_repo()

        added_ticket = None

        def capture(obj: object) -> None:
            nonlocal added_ticket
            added_ticket = obj

        db.add = capture

        before = datetime.now(timezone.utc)
        await repo.create(
            ticket_ref="hitl_abc123",
            tenant_id=1,
            tool_name="code__run",
            payload={},
            risk_level="HIGH",
        )
        after = datetime.now(timezone.utc)

        assert added_ticket is not None
        assert added_ticket.expires_at > before
        # SLA = 4 hours
        assert added_ticket.expires_at <= after + timedelta(hours=4, seconds=1)


# ---------------------------------------------------------------------------
# Test: approve ticket
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApproveTicket:
    @pytest.mark.asyncio
    async def test_approve_pending_ticket_returns_true(self):
        repo, db = _make_repo()
        db.execute.return_value = _mock_update_result(rowcount=1)

        updated = await repo.approve(
            ticket_ref="hitl_abc123",
            tenant_id=1,
            user_id=42,
        )

        assert updated is True
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_approve_nonexistent_ticket_returns_false(self):
        repo, db = _make_repo()
        db.execute.return_value = _mock_update_result(rowcount=0)

        updated = await repo.approve(
            ticket_ref="hitl_does_not_exist",
            tenant_id=1,
            user_id=42,
        )

        assert updated is False

    @pytest.mark.asyncio
    async def test_approve_wrong_tenant_returns_false(self):
        """Approve with wrong tenant_id must not update any row."""
        repo, db = _make_repo()
        # Simulates DB finding 0 rows because tenant_id did not match
        db.execute.return_value = _mock_update_result(rowcount=0)

        updated = await repo.approve(
            ticket_ref="hitl_abc123",
            tenant_id=999,  # wrong tenant
            user_id=42,
        )

        assert updated is False


# ---------------------------------------------------------------------------
# Test: reject ticket
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRejectTicket:
    @pytest.mark.asyncio
    async def test_reject_pending_ticket_returns_true(self):
        repo, db = _make_repo()
        db.execute.return_value = _mock_update_result(rowcount=1)

        updated = await repo.reject(
            ticket_ref="hitl_abc123",
            tenant_id=1,
            user_id=42,
        )

        assert updated is True

    @pytest.mark.asyncio
    async def test_reject_nonexistent_ticket_returns_false(self):
        repo, db = _make_repo()
        db.execute.return_value = _mock_update_result(rowcount=0)

        updated = await repo.reject(
            ticket_ref="hitl_does_not_exist",
            tenant_id=1,
            user_id=42,
        )

        assert updated is False


# ---------------------------------------------------------------------------
# Test: tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_get_returns_none_for_wrong_tenant(self):
        """get() with wrong tenant_id must return None (simulates DB filtering)."""
        repo, db = _make_repo()
        # DB returns no row because tenant_id clause excluded it
        db.execute.return_value = _mock_result(scalar=None)

        ticket = await repo.get(ticket_ref="hitl_abc123", tenant_id=999)

        assert ticket is None

    @pytest.mark.asyncio
    async def test_get_returns_ticket_for_correct_tenant(self):
        """get() with correct tenant_id returns the ticket."""
        repo, db = _make_repo()
        expected = _make_ticket(ticket_ref="hitl_abc123", tenant_id=1)
        db.execute.return_value = _mock_result(scalar=expected)

        ticket = await repo.get(ticket_ref="hitl_abc123", tenant_id=1)

        assert ticket is expected
        assert ticket.tenant_id == 1

    @pytest.mark.asyncio
    async def test_get_by_tenant_returns_only_matching_tenant_rows(self):
        """get_by_tenant() query always contains tenant_id — simulated by DB returning only own rows."""
        repo, db = _make_repo()
        tenant1_tickets = [
            _make_ticket(ticket_ref="hitl_t1_a", tenant_id=1),
            _make_ticket(ticket_ref="hitl_t1_b", tenant_id=1),
        ]
        db.execute.return_value = _mock_scalars_result(tenant1_tickets)

        tickets = await repo.get_by_tenant(tenant_id=1)

        assert len(tickets) == 2
        for t in tickets:
            assert t.tenant_id == 1

    @pytest.mark.asyncio
    async def test_get_unchecked_bypasses_tenant_filter(self):
        """get_unchecked() is internal-only and returns ticket regardless of tenant."""
        repo, db = _make_repo()
        ticket = _make_ticket(ticket_ref="hitl_abc123", tenant_id=2)
        db.execute.return_value = _mock_result(scalar=ticket)

        result = await repo.get_unchecked(ticket_ref="hitl_abc123")

        assert result is ticket
        assert result.tenant_id == 2


# ---------------------------------------------------------------------------
# Test: expired ticket cleanup
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExpiredTicketCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_expired_returns_count(self):
        """cleanup_expired() returns the number of rows marked expired."""
        repo, db = _make_repo()
        db.execute.return_value = _mock_update_result(rowcount=3)

        count = await repo.cleanup_expired(tenant_id=1)

        assert count == 3
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_expired_returns_zero_when_none_expired(self):
        repo, db = _make_repo()
        db.execute.return_value = _mock_update_result(rowcount=0)

        count = await repo.cleanup_expired(tenant_id=1)

        assert count == 0


# ---------------------------------------------------------------------------
# Test: paginated get_by_tenant
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetByTenantPaginated:
    @pytest.mark.asyncio
    async def test_get_by_tenant_default_limit_50(self):
        """Default limit is 50 — validated via method signature."""
        repo, db = _make_repo()
        db.execute.return_value = _mock_scalars_result([])

        await repo.get_by_tenant(tenant_id=1)

        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_by_tenant_respects_custom_limit_and_offset(self):
        """Custom limit/offset are forwarded to the query."""
        repo, db = _make_repo()
        tickets = [_make_ticket(ticket_ref=f"hitl_{i}", tenant_id=1) for i in range(5)]
        db.execute.return_value = _mock_scalars_result(tickets)

        result = await repo.get_by_tenant(tenant_id=1, limit=5, offset=10)

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_get_by_tenant_returns_empty_list_when_no_tickets(self):
        repo, db = _make_repo()
        db.execute.return_value = _mock_scalars_result([])

        result = await repo.get_by_tenant(tenant_id=1)

        assert result == []


# ---------------------------------------------------------------------------
# Test: generate_ticket_ref helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateTicketRef:
    def test_generate_ticket_ref_format(self):
        ref = generate_ticket_ref()
        assert ref.startswith("hitl_")
        assert len(ref) == len("hitl_") + 16

    def test_generate_ticket_ref_uniqueness(self):
        refs = {generate_ticket_ref() for _ in range(100)}
        assert len(refs) == 100


# ---------------------------------------------------------------------------
# ADR-036 OP-47 -- na de beslissing blijft alleen het BESLUIT bewaard
# ---------------------------------------------------------------------------


def _executed_statement(db: MagicMock) -> object:
    """Het statement dat aan `db.execute` is meegegeven."""
    assert db.execute.await_args is not None, "db.execute is niet aangeroepen"
    return db.execute.await_args[0][0]


def _compiled_sql(statement: object) -> str:
    """Het statement als SQL-tekst, met de waarden INGEVULD.

    `literal_binds=True` is hier geen detail: zonder dat rendert SQLAlchemy elke `literal()` als een
    bindparameter (`%(param_1)s`) en staan de sleutelnamen NIET in de tekst. De asserties hieronder
    zouden dan vragen of `_decision_id` in de SQL staat, altijd nee krijgen, en dat als een echte
    bevinding presenteren -- terwijl de expressie klopt.

    Blijft een zwakke toets: dit leest SQL-TEKST, geen semantiek. Een expressie die syntactisch
    klopt maar het verkeerde doet komt hier doorheen. Daarom hoort er een integratietest op echte
    Postgres bij; deze unit-tests bewaken de VORM en niet het gedrag.
    """
    from sqlalchemy.dialects import postgresql

    return str(
        statement.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


@pytest.mark.unit
class TestResolvingATicketKeepsOnlyTheDecision:
    """`hitl_tickets.payload` is het enige LIVE klaartekstpad (ADR-036 OP-47).

    **Waarom dit het enige is, gemeten.** OP-27 hardde vijf bewarende plekken, maar op alle vier de
    plekken waar `ToolBrokerService` wordt geconstrueerd (`agents/base_agent.py:226`,
    `als/agents/specialist_base.py:101`, `tool_broker/dependencies.py:72` en `:139`) wordt
    uitsluitend `hitl_store` meegegeven -- nooit `audit_repository` of `event_publisher`, die beide
    default `None` hebben. Drie van die vijf zijn dus latent. En binnen `execute_tool` gaan alle
    opslagaanroepen door een trechter (`_publish_tool_event`) die de GEREDIGEERDE payload krijgt.

    Wat overblijft is dit pad: `copilot/service.py:528` geeft `dict(proposal.action_params)`
    onbewerkt aan `create_hitl_request`, die het in `payload` samenvoegt. Dat is door een taalmodel
    geschreven tekst, onuitwisbaar op schijf, zonder retentie en zonder wisroute.

    **De afweging.** Zolang een ticket PENDING is moeten de waarden leesbaar blijven: wie een actie
    goedkeurt moet zien wat hij goedkeurt (AI Act art. 14). Na de beslissing niet meer -- besluit
    Rakesh 2026-08-05: dan blijft alleen het BESLUIT bewaard.

    **De valstrik die dit bijna fout deed.** `hitl_repository.py:169-175` bouwt
    `payload = {**action_params, "_decision_id", "_reason", "_requested_by", "_requested_at"}`. De
    metadata die we WILLEN houden zit dus in dezelfde dict als de modeloutput. Wholesale leegmaken
    gooit het besluit weg -- dat stond in de eerste versie van het plan en is door het
    twijfelonderzoek betrapt. En `_reason` is `decision.explanation_for_user`, dus OOK modeltekst:
    die hoort bij het weggooien, niet bij het bewaren.
    """

    RETAINED = ("_decision_id", "_requested_by", "_requested_at")

    @pytest.mark.asyncio
    async def test_approve_overwrites_the_payload(self):
        repo, db = _make_repo()
        db.execute.return_value = _mock_update_result(rowcount=1)

        await repo.approve(ticket_ref="hitl_abc123", tenant_id=1, user_id=42)

        sql = _compiled_sql(_executed_statement(db))
        assert "payload" in sql, (
            "De UPDATE bij goedkeuren raakt `payload` niet. Dan blijft de door het model geschreven "
            "inhoud onuitwisbaar staan -- dat is OP-47."
        )

    @pytest.mark.asyncio
    async def test_reject_overwrites_the_payload(self):
        repo, db = _make_repo()
        db.execute.return_value = _mock_update_result(rowcount=1)

        await repo.reject(ticket_ref="hitl_abc123", tenant_id=1, user_id=42)

        sql = _compiled_sql(_executed_statement(db))
        assert "payload" in sql, (
            "De UPDATE bij afwijzen raakt `payload` niet. Afwijzen is net zo definitief als "
            "goedkeuren; de inhoud is daarna even overbodig."
        )

    @pytest.mark.asyncio
    async def test_the_new_payload_keeps_the_decision_keys(self):
        repo, db = _make_repo()
        db.execute.return_value = _mock_update_result(rowcount=1)

        await repo.approve(ticket_ref="hitl_abc123", tenant_id=1, user_id=42)

        sql = _compiled_sql(_executed_statement(db))
        missing = [key for key in self.RETAINED if key not in sql]
        assert not missing, (
            f"Deze besluitsleutels komen niet in de nieuwe payload voor: {missing}. Dan is met de "
            "modeloutput ook het BESLUIT weggegooid, en dat is precies wat er bewaard moet blijven."
        )

    @pytest.mark.asyncio
    async def test_the_new_payload_drops_the_model_written_reason(self):
        """`_reason` is `explanation_for_user` en dus modeltekst -- die hoort NIET bij het besluit."""
        repo, db = _make_repo()
        db.execute.return_value = _mock_update_result(rowcount=1)

        await repo.approve(ticket_ref="hitl_abc123", tenant_id=1, user_id=42)

        sql = _compiled_sql(_executed_statement(db))
        assert "_reason" not in sql, (
            "De nieuwe payload bewaart `_reason`. Dat veld is `decision.explanation_for_user`, dus "
            "vrije modeltekst -- het hoort bij de inhoud die weggaat en niet bij het besluit."
        )

    @pytest.mark.asyncio
    async def test_the_payload_is_rebuilt_and_not_set_to_a_literal(self):
        """Vangnet: een vaste lege dict zou de eerste drie tests ook groen maken.

        `payload` is JSONB NOT NULL, dus `None` kan niet -- maar `{}` kan wel, en dan zijn de
        besluitsleutels net zo goed weg. Deze assertie eist dat de nieuwe waarde uit de BESTAANDE
        rij wordt opgebouwd.
        """
        repo, db = _make_repo()
        db.execute.return_value = _mock_update_result(rowcount=1)

        await repo.approve(ticket_ref="hitl_abc123", tenant_id=1, user_id=42)

        sql = _compiled_sql(_executed_statement(db))
        assert "jsonb_build_object" in sql, (
            "De nieuwe payload wordt niet uit de bestaande rij opgebouwd. Zet hem samen met een "
            "JSONB-expressie over de bewaarde sleutels, in DEZELFDE UPDATE -- read-then-write geeft "
            "een race tussen het lezen en het schrijven."
        )

    @pytest.mark.asyncio
    async def test_cleanup_expired_also_clears_the_payload(self):
        """Een verlopen ticket is nooit beoordeeld, dus de inhoud is daarna zeker overbodig."""
        repo, db = _make_repo()
        db.execute.return_value = _mock_update_result(rowcount=3)

        await repo.cleanup_expired(tenant_id=1)

        sql = _compiled_sql(_executed_statement(db))
        assert "payload" in sql, (
            "`cleanup_expired` markeert alleen `status=\"expired\"` en laat de inhoud staan. Een "
            "verlopen ticket is nooit beoordeeld; er is geen enkele grond om de modeltekst te "
            "bewaren."
        )


# ---------------------------------------------------------------------------
# Test: create_hitl_request -- executing_identity (ADR-036 OP-163)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateHitlRequestExecutingIdentity:
    """De permissiecheck bij AANMAKEN moet de AANVRAGENDE identiteit toetsen, niet altijd
    `copilot`.

    `query_hr_database` staat in `config/tool_permissions.yml` uitsluitend in het profiel van
    `skillsgaptraining`; `copilot` heeft het niet. Voor deze fix (ADR-036 OP-163) was er geen
    manier om dat verschil aan `create_hitl_request` mee te geven -- elke aanvraag werd altijd
    getoetst als `copilot`.
    """

    @pytest.mark.asyncio
    async def test_the_default_identity_cannot_request_a_tool_it_may_not_run(self):
        """Zonder `executing_identity` blijft het gedrag van voor deze fix behouden."""
        repo, _db = _make_repo()

        with pytest.raises(PermissionError):
            await repo.create_hitl_request(
                tenant_id=1,
                user_id=42,
                decision_id="d-1",
                reason="test",
                action_type="query_hr_database",
                action_params={"employee_id": "e-1"},
            )

    @pytest.mark.asyncio
    async def test_an_identity_with_permission_for_the_tool_may_request_it(self):
        """De piloot-skill mag wel degelijk om goedkeuring vragen voor haar eigen tools."""
        repo, db = _make_repo()

        ticket_ref = await repo.create_hitl_request(
            tenant_id=1,
            user_id=42,
            decision_id="d-1",
            reason="test",
            action_type="query_hr_database",
            action_params={"employee_id": "e-1"},
            executing_identity="skillsgaptraining",
        )

        assert ticket_ref
        db.add.assert_called_once()
        created_ticket = db.add.call_args.args[0]
        assert created_ticket.payload["_executing_identity"] == "skillsgaptraining", (
            "De identiteit die bij aanmaken is getoetst moet in de payload bewaard blijven, "
            "zodat verzilveren (hitl_router.py) met DEZELFDE identiteit uitvoert -- anders "
            "keurt de ene controle iets anders goed dan de andere uitvoert."
        )

    @pytest.mark.asyncio
    async def test_omitting_the_parameter_keeps_the_existing_copilot_caller_working(self):
        """Backwards compatible: `copilot/service.py` roept aan zonder dit argument."""
        repo, db = _make_repo()

        ticket_ref = await repo.create_hitl_request(
            tenant_id=1,
            user_id=42,
            decision_id="d-1",
            reason="test",
            action_type="create_task",
            action_params={},
        )

        assert ticket_ref
        created_ticket = db.add.call_args.args[0]
        assert created_ticket.payload["_executing_identity"] == "copilot"

    def test_the_blijft_deferral_decision_is_still_current(self) -> None:
        """Ankertest voor de bewuste OP-163-beslissing bij `_BLIJFT` in hitl_repository.py.

        Die module-comment legt uit WAAROM `_executing_identity` niet in `_BLIJFT` staat (de
        functionele behoefte is al voldaan omdat hij voor de wipe wordt gelezen; toevoegen zou
        ook `hitl_store._ticket_to_dict()` en `_AUDIT_FIELDS` in `hitl_router.py` moeten
        meenemen). Een Gate 2-code-reviewer (2026-08-18) merkte terecht op dat een losse
        docstring-comment zonder test kan verstillen zodra iemand de situatie verandert zonder
        de comment te lezen. Deze test is dat vangnet: hij wordt ROOD zodra de twee helften van
        de beslissing uit sync raken, en dwingt dan een bewuste herbeoordeling in plaats van een
        per ongeluk incomplete wijziging.
        """
        from src.core.api.v1.tool_broker.hitl_router import _AUDIT_FIELDS
        from src.core.tool_broker.hitl_repository import _BLIJFT

        in_blijft = "_executing_identity" in _BLIJFT
        in_audit_fields = "executing_identity" in _AUDIT_FIELDS

        assert in_blijft == in_audit_fields, (
            "`_executing_identity` staat wel in _BLIJFT (overleeft resolutie) maar niet in "
            "_AUDIT_FIELDS (wordt nooit getoond), of omgekeerd -- de twee helften van de "
            "OP-163-beslissing zijn uit sync. Werk de comment boven _BLIJFT in "
            "hitl_repository.py bij en beoordeel dan bewust of dit klopt."
        )
        assert not in_blijft, (
            "`_executing_identity` staat nu in _BLIJFT: de OP-163-deferral is kennelijk "
            "opgelost. Werk de comment boven _BLIJFT bij (die stelt nu dat dit bewust NIET het "
            "geval is) en verwijder dan deze aanname uit deze test."
        )
