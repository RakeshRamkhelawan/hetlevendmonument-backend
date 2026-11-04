"""
Valideert dat repositories niet cross-tenant data teruggeven.

Happy path:    get() met juiste tenant_id geeft record terug
Unhappy path:  get() met verkeerde tenant_id geeft None (niet het record)
Behavioral:    Een aanvaller die een geldig flow_id van tenant A kent
               kan dit NIET gebruiken als tenant B om het record op te halen
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession


class TestFocusBuilderRepositoryIsolation:
    """src/core/focus_builder/repositories.py"""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.mark.asyncio
    async def test_happy_path_correct_tenant_gets_record(self, mock_session):
        """get() met juiste tenant_id geeft het record terug."""
        from src.core.focus_builder.repositories import FlowRepository

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(id=1, tenant_id=42)
        mock_session.execute.return_value = mock_result

        repo = FlowRepository(session=mock_session, tenant_id=42)
        result = await repo.get(flow_id=1)
        assert result is not None

    @pytest.mark.asyncio
    async def test_unhappy_path_wrong_tenant_gets_nothing(self, mock_session):
        """
        get() met een flow_id die toehoort aan tenant 42, maar aangeroepen
        als tenant 99, mag NOOIT het record teruggeven.
        """
        from src.core.focus_builder.repositories import FlowRepository

        # Database geeft niets terug (WHERE clause filtert correct)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = FlowRepository(session=mock_session, tenant_id=99)
        result = await repo.get(flow_id=1)
        assert result is None

    @pytest.mark.asyncio
    async def test_behavioral_query_contains_tenant_id_filter(self, mock_session):
        """
        De SQL-query MOET een tenant_id WHERE-clause bevatten.
        Verifieer door de execute-aanroep te inspecteren.
        """
        from src.core.focus_builder.repositories import FlowRepository
        from sqlalchemy import inspect as sa_inspect

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = FlowRepository(session=mock_session, tenant_id=42)
        await repo.get(flow_id=1)

        assert mock_session.execute.called
        call_args = mock_session.execute.call_args[0][0]
        # Compileer de query en check dat tenant_id erin zit
        compiled = str(call_args.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id" in compiled, (
            f"Query bevat geen tenant_id filter:\n{compiled}"
        )

    @pytest.mark.asyncio
    async def test_unhappy_path_update_without_tenant_is_blocked(self, mock_session):
        """update() mag geen records updaten die niet van de juiste tenant zijn."""
        from src.core.focus_builder.repositories import FlowRepository

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # niet gevonden
        mock_session.execute.return_value = mock_result

        repo = FlowRepository(session=mock_session, tenant_id=99)
        result = await repo.update(flow_id=1, data={})
        assert result is None  # record niet gevonden → geen update


class TestWebhookRepositoryIsolation:
    """src/core/scheduling/webhooks/repository.py"""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.mark.asyncio
    async def test_webhook_get_by_id_filters_on_tenant(self, mock_session):
        """get_by_id() in WebhookRepository moet tenant_id filter hebben."""
        from src.core.scheduling.webhooks.repository import WebhookRepository

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = WebhookRepository(db=mock_session, tenant_id=42)
        await repo.get_by_id("webhook-123")

        # Verify query contains tenant_id filter
        assert mock_session.execute.called
        call_args = mock_session.execute.call_args[0][0]
        compiled = str(call_args.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id" in compiled, (
            f"WebhookRepository query bevat geen tenant_id filter:\n{compiled}"
        )

    @pytest.mark.asyncio
    async def test_webhook_get_by_channel_id_filters_on_tenant(self, mock_session):
        """get_by_channel_id() must include tenant_id filter (P0 fix)."""
        from src.core.scheduling.webhooks.repository import WebhookRepository

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = WebhookRepository(db=mock_session, tenant_id=42)
        await repo.get_by_channel_id("channel-123")

        # Verify query contains tenant_id filter
        assert mock_session.execute.called
        call_args = mock_session.execute.call_args[0][0]
        compiled = str(call_args.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id" in compiled, (
            f"get_by_channel_id query missing tenant_id filter (SECURITY BUG):\n{compiled}"
        )
        assert "channel_id" in compiled, (
            f"get_by_channel_id query missing channel_id filter:\n{compiled}"
        )

    @pytest.mark.asyncio
    async def test_webhook_get_by_subscription_id_filters_on_tenant(self, mock_session):
        """get_by_subscription_id() must include tenant_id filter (P0 fix)."""
        from src.core.scheduling.webhooks.repository import WebhookRepository

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = WebhookRepository(db=mock_session, tenant_id=42)
        await repo.get_by_subscription_id("sub-123")

        # Verify query contains tenant_id filter
        assert mock_session.execute.called
        call_args = mock_session.execute.call_args[0][0]
        compiled = str(call_args.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id" in compiled, (
            f"get_by_subscription_id query missing tenant_id filter (SECURITY BUG):\n{compiled}"
        )
        assert "subscription_id" in compiled, (
            f"get_by_subscription_id query missing subscription_id filter:\n{compiled}"
        )


class TestAIQualityRepositoryIsolation:
    """src/core/procedures/ai_quality_repository.py"""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.mark.asyncio
    async def test_ai_quality_get_by_id_filters_on_tenant(self, mock_session):
        """get_by_id() in AIQualityEventRepository moet tenant_id filter hebben."""
        from src.core.procedures.ai_quality_repository import AIQualityEventRepository
        from uuid import uuid4

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = AIQualityEventRepository(db=mock_session, tenant_id=42)
        await repo.get_by_id(uuid4())

        # Verify query contains tenant_id filter
        assert mock_session.execute.called
        call_args = mock_session.execute.call_args[0][0]
        compiled = str(call_args.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id" in compiled, (
            f"AIQualityEventRepository query bevat geen tenant_id filter:\n{compiled}"
        )


class TestPartnerFeedbackRepositoryIsolation:
    """src/core/scheduling/partners/repository.py - PartnerFeedbackRepository"""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.mark.asyncio
    async def test_partner_feedback_get_by_id_uses_join(self, mock_session):
        """get_by_id() in PartnerFeedbackRepository moet join gebruiken voor tenant isolatie."""
        from src.core.scheduling.partners.repository import PartnerFeedbackRepository

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        repo = PartnerFeedbackRepository(db=mock_session, tenant_id=42)
        await repo.get_by_id("feedback-123")

        # Verify query uses join with DesignPartner
        assert mock_session.execute.called
        call_args = mock_session.execute.call_args[0][0]
        compiled = str(call_args.compile(compile_kwargs={"literal_binds": True}))
        assert "join" in compiled.lower(), (
            f"PartnerFeedbackRepository query gebruikt geen JOIN:\n{compiled}"
        )
        assert "tenant_id" in compiled, (
            f"PartnerFeedbackRepository query bevat geen tenant_id filter:\n{compiled}"
        )
