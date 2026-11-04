"""Tests for AlertManager Phase 5 extensions.

Auto-remediation for MISSING_ATTRIBUTION (Art. 52/53).
Daily digest aggregation (alert fatigue reduction).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

# ---------------------------------------------------------------------------
# Auto-remediation: MISSING_ATTRIBUTION
# ---------------------------------------------------------------------------


class TestAlertManagerAutoRemediation:
    """auto_remediate() resolves missing attribution violations."""

    @pytest.mark.asyncio
    async def test_auto_remediate_method_exists(self) -> None:
        from src.core.governance.alert_manager import AlertManager

        assert hasattr(AlertManager, "auto_remediate")

    @pytest.mark.asyncio
    async def test_auto_remediate_is_async(self) -> None:
        import inspect

        from src.core.governance.alert_manager import AlertManager

        assert inspect.iscoroutinefunction(AlertManager.auto_remediate)

    @pytest.mark.asyncio
    async def test_auto_remediate_missing_attribution_returns_label(self) -> None:
        """MISSING_ATTRIBUTION → returns an AttributionLabel."""
        db = MagicMock()
        manager = __import__(
            "src.core.governance.alert_manager", fromlist=["AlertManager"]
        ).AlertManager(db)

        result = await manager.auto_remediate(
            tenant_id=1,
            agent_name="BotX",
            violation_type="missing_attribution",
            details={"provider": "openai", "model": "gpt-4"},
        )
        from src.core.governance.attribution import AttributionLabel

        assert isinstance(result, AttributionLabel)

    @pytest.mark.asyncio
    async def test_auto_remediate_attribution_has_provider(self) -> None:
        from src.core.governance.alert_manager import AlertManager

        manager = AlertManager(MagicMock())

        result = await manager.auto_remediate(
            tenant_id=1,
            agent_name="BotX",
            violation_type="missing_attribution",
            details={"provider": "openai", "model": "gpt-4"},
        )
        assert result.provider == "openai"

    @pytest.mark.asyncio
    async def test_auto_remediate_attribution_has_model(self) -> None:
        from src.core.governance.alert_manager import AlertManager

        manager = AlertManager(MagicMock())

        result = await manager.auto_remediate(
            tenant_id=1,
            agent_name="BotX",
            violation_type="missing_attribution",
            details={"provider": "anthropic", "model": "claude-3"},
        )
        assert result.model == "claude-3"

    @pytest.mark.asyncio
    async def test_auto_remediate_saves_learning_insight(self) -> None:
        """Auto-remediation saves a LearningInsight to close the learning loop."""
        from src.core.governance.alert_manager import AlertManager

        insight_repo = MagicMock()
        insight_repo.save = AsyncMock(return_value="id")

        manager = AlertManager(MagicMock(), insight_repo=insight_repo)

        await manager.auto_remediate(
            tenant_id=3,
            agent_name="BotZ",
            violation_type="missing_attribution",
            details={"provider": "openai", "model": "gpt-4"},
        )

        insight_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_remediate_insight_category_is_auto_remediation(self) -> None:
        from src.core.governance.alert_manager import AlertManager

        insight_repo = MagicMock()
        insight_repo.save = AsyncMock(return_value="id")

        manager = AlertManager(MagicMock(), insight_repo=insight_repo)
        await manager.auto_remediate(
            tenant_id=3,
            agent_name="BotZ",
            violation_type="missing_attribution",
            details={"provider": "openai", "model": "gpt-4"},
        )

        saved = insight_repo.save.call_args.args[0]
        assert saved.category == "auto_remediation"

    @pytest.mark.asyncio
    async def test_auto_remediate_unsupported_type_returns_none(self) -> None:
        """Violation types without remediation strategy return None."""
        from src.core.governance.alert_manager import AlertManager

        manager = AlertManager(MagicMock())

        result = await manager.auto_remediate(
            tenant_id=1,
            agent_name="BotX",
            violation_type="accuracy_drift",
            details={},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_auto_remediate_no_insight_repo_does_not_raise(self) -> None:
        """Without insight_repo, remediation still returns label (graceful)."""
        from src.core.governance.alert_manager import AlertManager

        manager = AlertManager(MagicMock())  # no insight_repo

        result = await manager.auto_remediate(
            tenant_id=1,
            agent_name="BotX",
            violation_type="missing_attribution",
            details={"provider": "openai", "model": "gpt-4"},
        )
        from src.core.governance.attribution import AttributionLabel

        assert isinstance(result, AttributionLabel)


# ---------------------------------------------------------------------------
# Daily digest
# ---------------------------------------------------------------------------


class TestAlertManagerDailyDigest:
    """generate_daily_digest() aggregates open alerts per tenant."""

    @pytest.mark.asyncio
    async def test_generate_daily_digest_method_exists(self) -> None:
        from src.core.governance.alert_manager import AlertManager

        assert hasattr(AlertManager, "generate_daily_digest")

    @pytest.mark.asyncio
    async def test_generate_daily_digest_is_async(self) -> None:
        import inspect

        from src.core.governance.alert_manager import AlertManager

        assert inspect.iscoroutinefunction(AlertManager.generate_daily_digest)

    @pytest.mark.asyncio
    async def test_daily_digest_returns_dict(self) -> None:
        from src.core.governance.alert_manager import AlertManager

        db = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            )
        )
        manager = AlertManager(db)

        result = await manager.generate_daily_digest(tenant_id=1)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_daily_digest_has_required_keys(self) -> None:
        """Digest must have tenant_id, date, total_alerts, by_severity."""
        from src.core.governance.alert_manager import AlertManager

        db = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            )
        )
        manager = AlertManager(db)

        result = await manager.generate_daily_digest(tenant_id=5)
        for key in ("tenant_id", "date", "total_alerts", "by_severity"):
            assert key in result, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_daily_digest_tenant_id_matches(self) -> None:
        from src.core.governance.alert_manager import AlertManager

        db = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            )
        )
        manager = AlertManager(db)

        result = await manager.generate_daily_digest(tenant_id=42)
        assert result["tenant_id"] == 42

    @pytest.mark.asyncio
    async def test_daily_digest_counts_alerts_by_severity(self) -> None:
        """by_severity is a dict mapping severity → count."""
        from src.core.governance.alert_manager import AlertManager

        db = MagicMock()
        # Two mock alerts: one CRITICAL, one HIGH
        crit = MagicMock()
        crit.severity = "critical"
        high = MagicMock()
        high.severity = "high"
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[crit, high])))
            )
        )
        manager = AlertManager(db)

        result = await manager.generate_daily_digest(tenant_id=1)
        assert result["by_severity"].get("critical", 0) >= 1
        assert result["by_severity"].get("high", 0) >= 1

    @pytest.mark.asyncio
    async def test_daily_digest_total_matches_sum(self) -> None:
        from src.core.governance.alert_manager import AlertManager

        db = MagicMock()
        alerts = [MagicMock(severity="medium") for _ in range(3)]
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=alerts)))
            )
        )
        manager = AlertManager(db)

        result = await manager.generate_daily_digest(tenant_id=1)
        assert result["total_alerts"] == 3

    @pytest.mark.asyncio
    async def test_daily_digest_date_is_today(self) -> None:
        from datetime import datetime
        from src.core.governance.alert_manager import AlertManager

        db = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            )
        )
        manager = AlertManager(db)

        result = await manager.generate_daily_digest(tenant_id=1)
        assert result["date"] == datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# AlertManager init accepts optional insight_repo
# ---------------------------------------------------------------------------


class TestAlertManagerInitPhase5:
    """AlertManager accepts optional insight_repo for auto-remediation."""

    def test_init_accepts_insight_repo(self) -> None:
        from src.core.governance.alert_manager import AlertManager

        repo = MagicMock()
        manager = AlertManager(db=MagicMock(), insight_repo=repo)
        assert manager._insight_repo is repo

    def test_init_insight_repo_defaults_to_none(self) -> None:
        from src.core.governance.alert_manager import AlertManager

        manager = AlertManager(db=MagicMock())
        assert manager._insight_repo is None
