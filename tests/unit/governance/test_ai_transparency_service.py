"""
Unit tests for AITransparencyService - GDPR Art. 13, 14, 21, 22 compliance.

TDD Workflow: RED phase - Write failing test first.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

# These imports will fail initially - that's the RED phase
from src.core.governance.ai_transparency_service import (
    AIDecisionRecord,
    AITransparencyService,
    ExplanationRequiredError,
    HumanReviewRequest,
    ProfilingType,
)
from src.core.governance.models import AuditLog


@pytest.mark.unit
@pytest.mark.gdpr
class TestAIDecisionLogging:
    """Test suite for GDPR Art. 13/14 - Transparency about AI processing."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = AsyncMock()
        # scalar_one_or_none returns None = user has not opted out of profiling (GDPR Art. 21)
        db.execute.return_value.scalar_one_or_none.return_value = None
        return db

    async def test_ai_decision_logged_with_explanation(self, mock_db):
        """AI decisions MUST be logged with human-readable explanation."""
        # Arrange
        service = AITransparencyService(mock_db)
        service.check_profiling_opt_out = AsyncMock(return_value=False)

        # Act
        decision = await service.log_ai_decision(
            user_id="user_123",
            tenant_id=1,
            agent_id="agent_456",
            decision_type="workflow_recommendation",
            input_data={"user_context": "HR manager, 5 years experience"},
            output_data={"recommended_workflow": "hr_onboarding_v2"},
            confidence_score=0.85,
            explanation=(
                "User profile indicates HR role with onboarding experience. "
                "Recommended hr_onboarding_v2 based on role match and seniority."
            ),
            profiling_involved=True,
            human_review_available=True,
        )

        # Assert
        assert isinstance(decision, AIDecisionRecord)
        assert decision.explanation is not None
        assert len(decision.explanation) > 0
        assert "HR role" in decision.explanation
        assert decision.human_review_available is True
        assert decision.profiling_involved is True

    async def test_ai_decision_explanation_is_required(self, mock_db):
        """AI decision MUST have explanation (Art. 13/14 requirement)."""
        # Arrange
        service = AITransparencyService(mock_db)

        # Act & Assert
        with pytest.raises(ExplanationRequiredError) as exc_info:
            await service.log_ai_decision(
                user_id="user_123",
                tenant_id=1,
                agent_id="agent_456",
                decision_type="workflow_recommendation",
                input_data={},
                output_data={},
                confidence_score=0.85,
                explanation="",  # Empty explanation - should fail
            )

        assert "explanation" in str(exc_info.value).lower()

    async def test_ai_decision_creates_audit_log(self, mock_db):
        """AI decision must create audit log entry."""
        # Arrange
        service = AITransparencyService(mock_db)

        # Act
        await service.log_ai_decision(
            user_id="user_123",
            tenant_id=1,
            agent_id="agent_456",
            decision_type="workflow_recommendation",
            input_data={},
            output_data={},
            confidence_score=0.85,
            explanation="Test explanation",
        )

        # Assert
        mock_db.add.assert_called()
        mock_db.commit.assert_called()

    async def test_input_data_is_minimized(self, mock_db):
        """Input data must be minimized for privacy (data minimization)."""
        # Arrange
        service = AITransparencyService(mock_db)

        input_data = {
            "name": "John Doe",  # PII - should be minimized
            "email": "john@example.com",  # PII - should be minimized
            "role": "HR Manager",  # Decision-relevant
            "department": "HR",  # Decision-relevant
        }

        # Act
        decision = await service.log_ai_decision(
            user_id="user_123",
            tenant_id=1,
            agent_id="agent_456",
            decision_type="workflow_recommendation",
            input_data=input_data,
            output_data={},
            confidence_score=0.85,
            explanation="Test explanation",
        )

        # Assert: PII should not be in logged data
        assert "name" not in str(decision.input_data_summary)
        assert "email" not in str(decision.input_data_summary)


@pytest.mark.unit
@pytest.mark.gdpr
class TestHumanReview:
    """Test suite for GDPR Art. 22(3) - Right to human review."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = AsyncMock()
        return db

    async def test_human_review_can_be_requested(self, mock_db):
        """User must be able to request human review of AI decision."""
        # Arrange
        service = AITransparencyService(mock_db)

        # Act
        review = await service.request_human_review(
            decision_id="dec_123",
            user_id="user_456",
            reason="I disagree with the workflow recommendation",
        )

        # Assert
        assert isinstance(review, HumanReviewRequest)
        assert review.status == "pending"
        assert review.estimated_resolution_days == 14
        assert "human review" in review.user_rights[0].lower()

    async def test_human_review_creates_audit_log(self, mock_db):
        """Human review request must be audited."""
        # Arrange
        service = AITransparencyService(mock_db)

        # Act
        await service.request_human_review(
            decision_id="dec_123",
            user_id="user_456",
            reason="Test reason",
        )

        # Assert
        mock_db.add.assert_called()
        call_args = mock_db.add.call_args[0][0]
        assert call_args.action == "ai.human_review_requested"

    async def test_human_review_logs_gdpr_article_reference(self, mock_db):
        """Audit log must reference GDPR Art. 22(3)."""
        # Arrange
        service = AITransparencyService(mock_db)

        # Act
        await service.request_human_review(
            decision_id="dec_123",
            user_id="user_456",
            reason="Test reason",
        )

        # Assert
        mock_db.add.assert_called()
        call_args = mock_db.add.call_args[0][0]
        assert call_args.event_metadata.get("gdpr_article") == "22(3)"


@pytest.mark.unit
@pytest.mark.gdpr
class TestProfilingOptOut:
    """Test suite for GDPR Art. 21 - Right to object to profiling."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = AsyncMock()
        return db

    def _create_mock_opt_out_record(self, opted_out=True):
        """Create mock opt-out record."""
        record = MagicMock()
        record.opted_out = opted_out
        record.user_id = 123
        record.tenant_id = 1
        record.profiling_type = ProfilingType.BEHAVIORAL
        return record

    async def test_user_can_opt_out_of_profiling(self, mock_db):
        """User must be able to opt out of profiling."""
        # Arrange
        service = AITransparencyService(mock_db)

        # Act
        await service.set_profiling_opt_out(
            user_id="user_123",
            tenant_id=1,
            profiling_type=ProfilingType.BEHAVIORAL,
            opt_out=True,
        )

        # Assert
        mock_db.add.assert_called()
        mock_db.commit.assert_called()

    async def test_profiling_opt_out_is_logged(self, mock_db):
        """Profiling opt-out must be audited."""
        # Arrange
        service = AITransparencyService(mock_db)

        # Act
        await service.set_profiling_opt_out(
            user_id="user_123",
            tenant_id=1,
            profiling_type=ProfilingType.BEHAVIORAL,
            opt_out=True,
        )

        # Assert
        mock_db.add.assert_called()
        call_args = mock_db.add.call_args[0][0]
        assert call_args.action == "ai.profiling_opt_out_changed"
        assert call_args.event_metadata.get("gdpr_article") == "21"

    async def test_check_profiling_opt_out_returns_true_when_opted_out(self, mock_db):
        """check_profiling_opt_out must return True when user opted out."""
        # Arrange
        service = AITransparencyService(mock_db)

        # Set up mock to return an opt-out record with opted_out=True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = self._create_mock_opt_out_record(
            opted_out=True
        )
        mock_db.execute.return_value = mock_result

        # Act
        is_opted_out = await service.check_profiling_opt_out(
            user_id="user_123",
            tenant_id=1,
            profiling_type=ProfilingType.BEHAVIORAL,
        )

        # Assert - user has opted out
        assert is_opted_out is True

    async def test_check_profiling_opt_out_returns_false_when_not_opted_out(self, mock_db):
        """check_profiling_opt_out must return False when user not opted out."""
        # Arrange
        service = AITransparencyService(mock_db)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        is_opted_out = await service.check_profiling_opt_out(
            user_id="user_123",
            tenant_id=1,
            profiling_type=ProfilingType.BEHAVIORAL,
        )

        # Assert
        assert is_opted_out is False

    async def test_user_can_opt_back_in(self, mock_db):
        """User must be able to opt back in (withdraw opt-out)."""
        # Arrange
        service = AITransparencyService(mock_db)

        # Act - this should create an audit log entry
        await service.set_profiling_opt_out(
            user_id="user_123",
            tenant_id=1,
            profiling_type=ProfilingType.BEHAVIORAL,
            opt_out=False,  # Opt back in
        )

        # Assert - verify audit log was created
        mock_db.add.assert_called()
        mock_db.commit.assert_called()


@pytest.mark.unit
@pytest.mark.gdpr
class TestProfilingTypes:
    """Test suite for different types of profiling."""

    def test_profiling_type_behavioral(self):
        """BEHAVIORAL profiling type must exist."""
        assert ProfilingType.BEHAVIORAL == "behavioral"

    def test_profiling_type_preference(self):
        """PREFERENCE profiling type must exist."""
        assert ProfilingType.PREFERENCE == "preference"

    def test_profiling_type_predictive(self):
        """PREDICTIVE profiling type must exist."""
        assert ProfilingType.PREDICTIVE == "predictive"

    def test_profiling_type_automated_decision(self):
        """AUTOMATED_DECISION profiling type must exist."""
        assert ProfilingType.AUTOMATED_DECISION == "automated_decision"


# Mark file as test file for pytest
__test__ = True


# ============================================================================
# ADR-036 OP-155 -- bezwaar tegen profilering faalt CLOSED, ook zonder context
# ============================================================================


class TestBezwaarTegenProfileringFaaltClosed:
    """Een lege tenantcontext mag op PostgreSQL geen 'geen bezwaar' opleveren.

    **Waarom dit bestaat.** `check_profiling_opt_out` faalt van nature OPEN: geen rij
    betekent "geen bezwaar". Dat is juist zolang de query alle rijen kan zien. Sinds
    `20260915_rls_resterende_tabellen.py` heeft `user_profiling_opt_outs` een RLS-policy,
    en dan geeft een LEGE tenantcontext nul rijen -- wat als "geen bezwaar" leest terwijl
    het "niet zichtbaar" betekent. Dat keert AVG art. 21 om: profilering gaat door tegen
    een uitdrukkelijk bezwaar in.

    Tot 2026-09-16 weigerde deze functie alleen bij een BOTSENDE context. Beide Gate
    2-reviews wezen daar onafhankelijk op.

    **Mutatiebewijs (2026-09-16), beide richtingen:**
    1. De `context_tenant is None and is_postgres`-tak weghalen ->
       `test_zonder_tenantcontext_weigert_hij_op_postgres` ROOD.
    2. De dialect-controle weghalen (dus ook op SQLite weigeren) ->
       `test_op_sqlite_blijft_een_lege_context_toegestaan` ROOD. Zonder die helft zou
       "weiger altijd" een geldige oplossing zijn en vallen de unit-tests massaal om op
       iets wat op SQLite niet kan gebeuren.
    """

    @staticmethod
    def _db(dialect: str):
        class _Dialect:
            name = dialect

        class _Bind:
            dialect = _Dialect()

        class _Db:
            bind = _Bind()

            async def execute(self, *_args, **_kwargs):  # pragma: no cover - niet bereikt
                raise AssertionError(
                    "De query had niet uitgevoerd mogen worden: de functie hoort te weigeren "
                    "voor hij de database raakt."
                )

        return _Db()

    def test_zonder_tenantcontext_weigert_hij_op_postgres(self) -> None:
        import asyncio

        from src.core.governance.ai_transparency_service import (
            AITransparencyService,
            ProfilingType,
        )
        from src.core.middleware.tenant_context import clear_tenant_context

        clear_tenant_context()
        dienst = AITransparencyService(self._db("postgresql"))

        async def probeer() -> None:
            await dienst.check_profiling_opt_out(
                user_id="u1", tenant_id=1, profiling_type=list(ProfilingType)[0]
            )

        with pytest.raises(ValueError, match="GEEN tenantcontext"):
            asyncio.run(probeer())

    def test_op_sqlite_blijft_een_lege_context_toegestaan(self) -> None:
        """De tegenrichting: SQLite kent geen RLS, dus daar is leeg echt onschuldig."""
        import asyncio

        from src.core.governance.ai_transparency_service import (
            AITransparencyService,
            ProfilingType,
        )
        from src.core.middleware.tenant_context import clear_tenant_context

        clear_tenant_context()
        dienst = AITransparencyService(self._db("sqlite"))

        async def probeer() -> None:
            await dienst.check_profiling_opt_out(
                user_id="u1", tenant_id=1, profiling_type=list(ProfilingType)[0]
            )

        # De stub-db werpt zodra de query WEL wordt uitgevoerd; dat bewijst dat de functie
        # niet eerder heeft geweigerd. Een ValueError zou betekenen dat de dialect-controle
        # ontbreekt.
        with pytest.raises(AssertionError, match="had niet uitgevoerd mogen worden"):
            asyncio.run(probeer())
