"""Integration tests for Gatekeeper API endpoints.

Tests the REST API surface for:
- Listing decisions with pagination
- Getting decisions by task
- Chain verification
- HITL approval/rejection workflows
- Statistics endpoint

ADR-017: Deterministic policy enforcement
ADR-005: Tenant isolation
ADR-019: SHA-256 hash chain
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from tests.integration._goedkeurrecht import goedkeurder_gebruikers  # noqa: F401
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.als.enterprise.gatekeeper_repository import GatekeeperRepository
from src.core.governance.governance_contract_repository import GovernanceContractRepository
from src.core.governance.models import GatekeeperDecision, HITLRequestModel

pytestmark = pytest.mark.usefixtures("goedkeurder_gebruikers")


@pytest.fixture(autouse=True)
def _csrf_uit(integration_app):
    """De CSRF-controle uitzetten voor DIT bestand (ADR-036 OP-80).

    De goedkeurroutes van de gatekeeper kregen op 2026-08-07 een `validate_csrf_token`-dependency.
    Die leunt op Redis en op een header die deze tests niet zetten, dus zonder override geeft elke
    state-wijzigende aanroep hier 403. Gemeten in CI: zeven tests in dit bestand vielen daarop om,
    en NIET lokaal -- de integratiesuite valt buiten het standaard testcommando.

    **Waarom hier en niet in de gedeelde clientfixture.** Daar heb ik het eerst gezet, en dat brak
    `test_auth_cookie_session.py::test_csrf_required_for_state_changing_request` -- die test
    controleert juist DAT een verzoek zonder token 403 geeft. Een override in een gedeelde fixture
    zet dus uit wat een andere test meet; precies de faalvorm die deze sprint als les heeft
    vastgelegd. Daarom bestandsgebonden.

    DAT de controle bestaat wordt bewezen door
    `tests/unit/api/test_gatekeeper_hitl_requires_an_approver.py::TestTheGatekeeperApprovalRoutesRequireACsrfToken`,
    die hem juist NIET overschrijft.
    """
    from src.core.api.auth.dependencies import validate_csrf_token

    integration_app.dependency_overrides[validate_csrf_token] = lambda: None
    yield
    integration_app.dependency_overrides.pop(validate_csrf_token, None)

@pytest_asyncio.fixture
async def sample_decisions(db_session: AsyncSession, test_tenant_id: int):
    """Create sample decisions for testing."""
    repo = GatekeeperRepository(db_session, test_tenant_id)

    decisions = []
    for i in range(5):
        decision = GatekeeperDecision(
            decision_id=f"dec-{i:04d}",
            task_id="task-001",
            tenant_id=test_tenant_id,
            decision="allow" if i % 2 == 0 else "block",
            risk_category="pii_access" if i % 2 == 0 else "financial_ops",
            risk_level="LOW" if i < 3 else "HIGH",
            hitl_required=i == 3,
            hitl_ticket_ref=f"HITL-{i:04d}" if i == 3 else None,
            override_used=False,
            decision_hash=f"hash-{i:064d}"[:64],  # 64 char hash
            previous_hash="genesis" if i == 0 else f"hash-{i - 1:064d}"[:64],
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(decision)
        decisions.append(decision)

    await db_session.commit()
    return decisions


@pytest_asyncio.fixture
async def sample_hitl_request_without_agent(db_session: AsyncSession, test_tenant_id: int):
    """Een wachtend ticket ZONDER agent: het proces is onbekend, dus niemand mag het beslissen."""
    hitl = HITLRequestModel(
        request_id="hitl-test-noagent-001",
        tenant_id=test_tenant_id,
        ticket_ref="HITL-TEST-NOAGENT-001",
        task_id="task-noagent-002",
        status="pending",
        risk_factors=["HIGH_RISK"],
        requested_by_user_id=2,
    )
    db_session.add(hitl)
    await db_session.commit()
    await db_session.refresh(hitl)
    return hitl


@pytest_asyncio.fixture
async def sample_hitl_request(db_session: AsyncSession, test_tenant_id: int):
    """Create a pending HITL request for testing."""
    hitl = HITLRequestModel(
        request_id="hitl-test-001",
        tenant_id=test_tenant_id,
        ticket_ref="HITL-TEST-001",
        task_id="task-002",
        status="pending",
        risk_factors=["HIGH_RISK", "PII_ACCESS"],
        # ADR-039: het goedkeurrecht hangt aan het proces van de agent; `dunning` -> receivables:approve.
        agent_id="dunning",
        # ADR-036 OP-81: sinds de goedkeurroute fail-closed is bij een ONHERLEIDBARE aanvrager
        # moet een ticket dat goedgekeurd MOET kunnen worden er een hebben. Gebruiker 2
        # (`user@integration.test`) en niet 1: 1 is de admin uit `admin_auth_headers`, en die zou
        # dan zijn eigen aanvraag goedkeuren -- dat is precies wat OP-81 verbiedt.
        requested_by_user_id=2,
    )
    db_session.add(hitl)
    await db_session.commit()
    await db_session.refresh(hitl)
    return hitl


@pytest_asyncio.fixture
async def sample_hitl_request_for_agent(db_session: AsyncSession, test_tenant_id: int):
    """A pending HITL request tied to a specific agent_id (SP-GOV-ARCH-7)."""
    hitl = HITLRequestModel(
        request_id="hitl-test-agent-001",
        tenant_id=test_tenant_id,
        ticket_ref="HITL-TEST-AGENT-001",
        task_id="task-agent-002",
        status="pending",
        risk_factors=["HIGH_RISK"],
        agent_id="dunning",
        # ADR-036 OP-81: sinds de goedkeurroute fail-closed is bij een ONHERLEIDBARE aanvrager
        # moet een ticket dat goedgekeurd MOET kunnen worden er een hebben. Gebruiker 2
        # (`user@integration.test`) en niet 1: 1 is de admin uit `admin_auth_headers`, en die zou
        # dan zijn eigen aanvraag goedkeuren -- dat is precies wat OP-81 verbiedt.
        requested_by_user_id=2,
    )
    db_session.add(hitl)
    await db_session.commit()
    await db_session.refresh(hitl)
    return hitl


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_decisions(client: AsyncClient, sample_decisions, auth_headers):
    """Test GET /api/v1/gatekeeper/decisions returns paginated decisions."""
    response = await client.get("/api/v1/gatekeeper/decisions", headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "data" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data

    assert data["total"] == 5
    assert len(data["data"]) <= data["limit"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_decisions_with_pagination(client: AsyncClient, sample_decisions, auth_headers):
    """Test pagination parameters work correctly."""
    response = await client.get(
        "/api/v1/gatekeeper/decisions?limit=2&offset=0", headers=auth_headers
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["data"]) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_decisions_filter_by_task(client: AsyncClient, sample_decisions, auth_headers):
    """Test filtering decisions by task_id."""
    response = await client.get(
        "/api/v1/gatekeeper/decisions?task_id=task-001", headers=auth_headers
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["total"] == 5
    for decision in data["data"]:
        assert decision["task_id"] == "task-001"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_decisions_by_task(client: AsyncClient, sample_decisions, auth_headers):
    """Test GET /api/v1/gatekeeper/decisions/{task_id}."""
    response = await client.get("/api/v1/gatekeeper/decisions/task-001", headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert isinstance(data, list)
    assert len(data) == 5

    # Verify chain links
    for i, decision in enumerate(data):
        assert "decision_id" in decision
        assert "decision_hash" in decision
        assert "previous_hash" in decision
        assert len(decision["decision_hash"]) == 64  # SHA-256 hex


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_decisions_by_task_not_found(client: AsyncClient, auth_headers):
    """Test 404 for non-existent task."""
    response = await client.get(
        "/api/v1/gatekeeper/decisions/nonexistent-task", headers=auth_headers
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verify_task_chain(client: AsyncClient, sample_decisions, auth_headers):
    """Test chain verification endpoint."""
    response = await client.get("/api/v1/gatekeeper/decisions/task-001/chain", headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["task_id"] == "task-001"
    assert data["chain_valid"] is True
    assert data["decisions_count"] == 5
    assert data["first_decision"] == "dec-0000"
    assert data["last_decision"] == "dec-0004"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verify_empty_task_chain(client: AsyncClient, auth_headers):
    """Test chain verification for task with no decisions."""
    response = await client.get(
        "/api/v1/gatekeeper/decisions/empty-task/chain", headers=auth_headers
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["task_id"] == "empty-task"
    assert data["chain_valid"] is True
    assert data["decisions_count"] == 0
    assert data["first_decision"] is None
    assert data["last_decision"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_approve_hitl(client: AsyncClient, sample_hitl_request, admin_auth_headers):
    """Test POST /api/v1/gatekeeper/hitl/approve."""
    payload = {
        "ticket_ref": "HITL-TEST-001",
        "approved_by": "admin@example.com",
        "notes": "Approved after review",
    }

    response = await client.post(
        "/api/v1/gatekeeper/hitl/approve", json=payload, headers=admin_auth_headers
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["status"] == "approved"
    assert data["ticket_ref"] == "HITL-TEST-001"
    assert "message" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_approve_hitl_not_found(client: AsyncClient, admin_auth_headers):
    """Test 404 when approving non-existent HITL."""
    payload = {
        "ticket_ref": "NONEXISTENT",
        "approved_by": "admin@example.com",
    }

    response = await client.post(
        "/api/v1/gatekeeper/hitl/approve", json=payload, headers=admin_auth_headers
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.integration
@pytest.mark.asyncio
async def test_approve_hitl_already_processed(
    client: AsyncClient, sample_hitl_request, admin_auth_headers
):
    """Test 400 when trying to approve already processed HITL."""
    # First approval
    await client.post(
        "/api/v1/gatekeeper/hitl/approve",
        json={"ticket_ref": "HITL-TEST-001", "approved_by": "admin@example.com"},
        headers=admin_auth_headers,
    )

    # Second approval should fail
    response = await client.post(
        "/api/v1/gatekeeper/hitl/approve",
        json={"ticket_ref": "HITL-TEST-001", "approved_by": "admin2@example.com"},
        headers=admin_auth_headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.integration
@pytest.mark.asyncio
async def test_approve_hitl_for_agent_ticket_records_governance_approval(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_hitl_request_for_agent,
    admin_auth_headers,
    test_tenant_id: int,
):
    """SP-GOV-ARCH-7: approving a HITL ticket tied to an agent persists a
    GovernanceContract approval. agent_id is derived server-side from the
    ticket (hitl.agent_id) -- NOT accepted as a client-supplied field, so a
    caller cannot graft an approval onto an unrelated agent's contract."""
    payload = {"ticket_ref": "HITL-TEST-AGENT-001", "approved_by": "admin@example.com"}

    response = await client.post(
        "/api/v1/gatekeeper/hitl/approve", json=payload, headers=admin_auth_headers
    )

    assert response.status_code == status.HTTP_200_OK

    repo = GovernanceContractRepository(db_session, test_tenant_id)
    contract = await repo.load("dunning")

    assert contract is not None
    assert "task-agent-002" in contract.evidence["approved_actions"]

    # ADR-036 OP-43 + OP-55: het art.-14-bewijs komt uit het TOKEN en is het ONVERANDERLIJKE
    # gebruikersnummer.
    #
    # De body draagt hierboven bewust nog `admin@example.com` -- dat veld bestaat nog in het schema
    # maar wordt genegeerd ("context wint", zoals `tool_broker/service.py:162` voor tenant_id doet).
    #
    # Deze assertie is twee keer bijgesteld en dat is leerzaam: tot 2026-08-05 verwachtte hij de
    # BODY-waarde (en sloeg daarmee vast wat OP-43 juist weghaalt), daarna het e-mailadres uit het
    # token -- tot de blinde review aantoonde dat een gebruiker dat adres zelf kan wijzigen via
    # `PUT /api/v1/users/me`. Nu het gebruikersnummer, dat hij niet kan wijzigen.
    #
    # Beide negatieve asserties staan er expliciet bij: zonder de eerste maakt terugdraaien naar de
    # body-waarde deze test weer groen, en zonder de tweede zou terugvallen op het adres dat ook doen.
    approver = contract.evidence["hitl_approval"][0]["approved_by"]
    assert approver == "user:1", (
        "de goedkeurder moet het onveranderlijke gebruikersnummer uit admin_auth_headers zijn "
        f"(user_id=1), niet {approver!r}"
    )
    assert approver != "admin@example.com", (
        "de body-waarde bepaalt het art.-14-bewijs weer -- OP-43 is teruggedraaid"
    )
    assert approver != "admin@integration.test", (
        "het bewijs is weer het e-mailadres, en dat kan de gebruiker zelf wijzigen -- OP-55 is "
        "teruggedraaid"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_approve_hitl_without_agent_id_is_refused_and_creates_no_contract(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_hitl_request_without_agent,
    admin_auth_headers,
    test_tenant_id: int,
):
    """ADR-039: een ticket zonder agent heeft geen bekend proces, dus geen goedkeurrecht dat erbij
    hoort: 403 (fail-closed), en er ontstaat geen contractrij."""
    payload = {"ticket_ref": "HITL-TEST-NOAGENT-001", "approved_by": "admin@example.com"}

    response = await client.post(
        "/api/v1/gatekeeper/hitl/approve", json=payload, headers=admin_auth_headers
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN

    repo = GovernanceContractRepository(db_session, test_tenant_id)
    contract = await repo.load("dunning")

    assert contract is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reject_hitl(client: AsyncClient, sample_hitl_request, admin_auth_headers):
    """Test POST /api/v1/gatekeeper/hitl/reject."""
    payload = {
        "ticket_ref": "HITL-TEST-001",
        "rejected_by": "security@example.com",
        "reason": "Risk too high - requires executive approval",
    }

    response = await client.post(
        "/api/v1/gatekeeper/hitl/reject", json=payload, headers=admin_auth_headers
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["status"] == "rejected"
    assert data["ticket_ref"] == "HITL-TEST-001"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reject_hitl_validation_error(client: AsyncClient, sample_hitl_request, admin_auth_headers):
    """Test validation error when rejection reason is too short."""
    payload = {
        "ticket_ref": "HITL-TEST-001",
        "rejected_by": "security@example.com",
        "reason": "No",  # Too short - min 10 chars
    }

    response = await client.post(
        "/api/v1/gatekeeper/hitl/reject", json=payload, headers=admin_auth_headers
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_stats(client: AsyncClient, sample_decisions, sample_hitl_request, auth_headers):
    """Test GET /api/v1/gatekeeper/stats."""
    response = await client.get("/api/v1/gatekeeper/stats", headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["total_decisions"] == 5
    assert data["allowed"] == 3  # indices 0, 2, 4
    assert data["blocked"] == 2  # indices 1, 3
    assert data["require_hitl"] == 1  # index 3
    assert data["hitl_pending"] == 1
    assert data["hitl_approved"] == 0
    assert data["hitl_rejected"] == 0
    assert data["chain_integrity"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_stats_empty(client: AsyncClient, auth_headers):
    """Test stats endpoint with no data."""
    response = await client.get("/api/v1/gatekeeper/stats", headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["total_decisions"] == 0
    assert data["chain_integrity"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tenant_isolation(
    client: AsyncClient, db_session: AsyncSession, sample_decisions, auth_headers
):
    """Test that decisions are isolated by tenant."""
    # Create decisions for a different tenant
    other_tenant_id = 999
    other_decision = GatekeeperDecision(
        decision_id="other-dec-001",
        task_id="other-task",
        tenant_id=other_tenant_id,
        decision="allow",
        risk_category="pii_access",
        risk_level="LOW",
        hitl_required=False,
        override_used=False,
        decision_hash="a" * 64,
        previous_hash="genesis",
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(other_decision)
    await db_session.commit()

    # Query with test tenant headers (tenant_id=1 from fixture)
    response = await client.get("/api/v1/gatekeeper/stats", headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Should only see 5 decisions, not the 6th from other tenant
    assert data["total_decisions"] == 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_decision_response_schema(client: AsyncClient, sample_decisions, auth_headers):
    """Test that decision response follows expected schema."""
    response = await client.get("/api/v1/gatekeeper/decisions", headers=auth_headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    for decision in data["data"]:
        # Verify all expected fields exist
        assert "decision_id" in decision
        assert "task_id" in decision
        assert "decision" in decision
        assert "risk_category" in decision
        assert "risk_level" in decision
        assert "hitl_required" in decision
        assert "decision_hash" in decision
        assert "previous_hash" in decision
        assert "timestamp" in decision

        # Verify types
        assert isinstance(decision["decision_hash"], str)
        assert len(decision["decision_hash"]) == 64  # SHA-256 hex


@pytest.mark.integration
@pytest.mark.asyncio
async def test_governance_contract_load_returns_none_when_missing(
    db_session: AsyncSession, test_tenant_id: int
):
    """load() returns None for an agent_id with no persisted contract."""
    repo = GovernanceContractRepository(db_session, test_tenant_id)

    contract = await repo.load("never-seen-agent")

    assert contract is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_governance_contract_load_or_create_persists_default(
    db_session: AsyncSession, test_tenant_id: int
):
    """load_or_create() persists a fresh default contract on first call."""
    repo = GovernanceContractRepository(db_session, test_tenant_id)

    created = await repo.load_or_create("fresh-agent")
    reloaded = await repo.load("fresh-agent")

    assert reloaded is not None
    assert reloaded.agent_id == created.agent_id
    assert reloaded.autonomy_level == created.autonomy_level
    assert reloaded.risk_category == created.risk_category


@pytest.mark.integration
@pytest.mark.asyncio
async def test_governance_contract_save_upserts_evidence(
    db_session: AsyncSession, test_tenant_id: int
):
    """save() updates the same row on a second call instead of inserting a duplicate."""
    repo = GovernanceContractRepository(db_session, test_tenant_id)
    contract = await repo.load_or_create("repeat-agent")

    contract.record_hitl_approval(approved_by="reviewer@example.com", action="do-the-thing")
    await repo.save(contract)

    reloaded = await repo.load("repeat-agent")

    assert reloaded is not None
    assert "do-the-thing" in reloaded.evidence["approved_actions"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_governance_contract_repository_tenant_isolation(db_session: AsyncSession):
    """Tenant A must not see tenant B's persisted governance contract (ADR-005)."""
    repo_a = GovernanceContractRepository(db_session, 1)
    repo_b = GovernanceContractRepository(db_session, 999)

    await repo_a.load_or_create("shared-agent-id")

    contract_from_b = await repo_b.load("shared-agent-id")

    assert contract_from_b is None
