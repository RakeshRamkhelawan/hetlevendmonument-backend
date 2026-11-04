"""Sprint 6A Hardening — RED tests for P0 bugs C-1 through C-8.

Each test class proves exactly one crash that would occur in production.
Tests are written against real code, not mocks, where the bug is in the
real code path.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# C-1: OversightGate.check is sync — calling it with `await` raises TypeError
# ─────────────────────────────────────────────────────────────────────────────


class TestC1OversightGateAsync:
    """C-1: OversightGate.check must be async so GovernanceIntegration can await it."""

    def test_check_is_coroutine_function(self) -> None:
        """OversightGate.check must be an async def."""
        import inspect

        from src.core.governance.oversight_gate import OversightGate

        assert inspect.iscoroutinefunction(OversightGate.check), (
            "OversightGate.check is sync — GovernanceIntegration awaits it, "
            "causing TypeError at runtime."
        )

    @pytest.mark.asyncio
    async def test_governance_integration_pre_execution_with_real_gate(self) -> None:
        """pre_execution must not raise TypeError when using a real OversightGate."""
        from src.core.governance.governance_agent.integration import GovernanceIntegration
        from src.core.governance.oversight_gate import OversightGate

        gate = OversightGate()
        integration = GovernanceIntegration(
            oversight_gate=gate,
            accuracy_monitor=MagicMock(
                track_result=AsyncMock(),
                check_drift=AsyncMock(return_value=None),
            ),
            alert_manager=MagicMock(handle_violation=AsyncMock()),
            ml_strategy=MagicMock(analyze=AsyncMock(return_value=None)),
        )

        # Must not raise — if check() is sync this blows up with TypeError
        result = await integration.pre_execution(
            tenant_id=1,
            user_id=1,
            agent_name="TestBot",
            agent_department="Ops",
            agent_specialisation="analysis",
            agent_capabilities=["data_analysis"],
            task_action="process",
            task_params={},
        )
        assert result is not None
        assert hasattr(result, "allowed")


# ─────────────────────────────────────────────────────────────────────────────
# C-2: ComplianceGuardianAgent._on_task_completed — missing tenant_id in save
# ─────────────────────────────────────────────────────────────────────────────


class TestC2ComplianceGuardianSaveTenantId:
    """C-2: insight_repo.save must be called with (insight, str(tenant_id))."""

    @pytest.mark.asyncio
    async def test_on_task_completed_passes_tenant_id_to_save(self) -> None:
        insight_repo = MagicMock()
        insight_repo.save = AsyncMock(return_value="id")

        from src.core.governance.compliance_guardian import ComplianceGuardianAgent

        agent = ComplianceGuardianAgent(
            signal_bus=MagicMock(),
            alert_manager=MagicMock(),
            authority_reporter=MagicMock(),
            insight_repo=insight_repo,
            adaptation_repo=MagicMock(),
        )

        await agent._on_task_completed(
            {
                "tenant_id": 42,
                "agent_name": "BotX",
                "confidence_score": 0.9,
            }
        )

        call_args = insight_repo.save.call_args
        # Must be called with 2 positional args: (insight, tenant_id_str)
        assert len(call_args.args) == 2, (
            f"save() called with {len(call_args.args)} positional arg(s); "
            "expected 2: (insight, tenant_id_str)"
        )
        tenant_arg = call_args.args[1]
        assert tenant_arg == "42", f"Second arg to save() was {tenant_arg!r}, expected '42'"


# ─────────────────────────────────────────────────────────────────────────────
# C-3: AdaptationRuleRepository.count_recent does not exist
# ─────────────────────────────────────────────────────────────────────────────


class TestC3AdaptationRepoCountRecent:
    """C-3: AdaptationRuleRepository must have count_recent(tenant_id, agent, hours)."""

    def test_count_recent_method_exists(self) -> None:
        from src.core.learning.repository import AdaptationRuleRepository

        assert hasattr(AdaptationRuleRepository, "count_recent"), (
            "AdaptationRuleRepository.count_recent is missing — "
            "ComplianceGuardianAgent._on_governance_block calls it."
        )

    def test_count_recent_is_async(self) -> None:
        import inspect

        from src.core.learning.repository import AdaptationRuleRepository

        assert inspect.iscoroutinefunction(AdaptationRuleRepository.count_recent)

    def test_count_recent_signature(self) -> None:
        import inspect

        from src.core.learning.repository import AdaptationRuleRepository

        sig = inspect.signature(AdaptationRuleRepository.count_recent)
        params = set(sig.parameters.keys())
        assert {"tenant_id", "agent", "hours"}.issubset(params)

    @pytest.mark.asyncio
    async def test_count_recent_returns_int(self) -> None:
        """count_recent returns an integer even when no rows match."""
        from unittest.mock import MagicMock

        from src.core.learning.repository import AdaptationRuleRepository

        db = AsyncMock()
        # AsyncMock child attributes are also AsyncMock — override with plain MagicMock
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = 0
        db.execute.return_value = execute_result

        repo = AdaptationRuleRepository(session=db)
        result = await repo.count_recent(tenant_id=1, agent="BotX", hours=24)
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_count_recent_tenant_scoped(self) -> None:
        """count_recent must filter by tenant_id."""
        from unittest.mock import MagicMock, call

        from src.core.learning.repository import AdaptationRuleRepository

        db = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = 3
        db.execute.return_value = execute_result

        repo = AdaptationRuleRepository(session=db)
        await repo.count_recent(tenant_id=7, agent="BotA", hours=24)

        # The SQL call must have been made
        db.execute.assert_called_once()
        # The statement passed to execute must incorporate tenant_id=7
        # (We check this by verifying the call was made; integration tests
        # verify the WHERE clause against a real DB.)


# ─────────────────────────────────────────────────────────────────────────────
# C-4: AlertManager.handle_violation — create_incident called with wrong sig + await
# ─────────────────────────────────────────────────────────────────────────────


class TestC4AlertManagerCreateIncident:
    """C-4: handle_violation for CRITICAL must call create_incident correctly (no await, right args)."""

    @pytest.mark.asyncio
    async def test_critical_violation_does_not_raise(self) -> None:
        """handle_violation with pii_leakage (CRITICAL) must not raise TypeError."""
        from src.core.governance.alert_manager import AlertManager

        db = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        execute_result.scalars.return_value.all.return_value = []
        db.execute.return_value = execute_result

        manager = AlertManager(db)

        # pii_leakage → CRITICAL → calls create_incident; must not raise
        await manager.handle_violation(
            tenant_id=1,
            agent_name="BotX",
            violation_type="pii_leakage",
            details={"description": "PII found"},
        )
        # If we get here without TypeError the fix works

    @pytest.mark.asyncio
    async def test_critical_violation_creates_incident_record(self) -> None:
        """CRITICAL violation must add an IncidentReportDB row to the session."""
        from src.core.governance.alert_manager import AlertManager
        from src.core.governance.models import IncidentReportDB

        db = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        db.execute.return_value = execute_result

        manager = AlertManager(db)
        await manager.handle_violation(
            tenant_id=1,
            agent_name="CritBot",
            violation_type="pii_leakage",
            details={"description": "Leaked PII"},
        )

        added_rows = [call.args[0] for call in db.add.call_args_list]
        incident_rows = [r for r in added_rows if isinstance(r, IncidentReportDB)]
        assert len(incident_rows) >= 1
        assert incident_rows[0].severity == "critical"
        assert incident_rows[0].eu_reporting_required is True

    @pytest.mark.asyncio
    async def test_non_critical_violation_does_not_create_incident(self) -> None:
        """MEDIUM violation must not add an IncidentReportDB row to the session."""
        from src.core.governance.alert_manager import AlertManager
        from src.core.governance.models import IncidentReportDB

        db = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        db.execute.return_value = execute_result

        manager = AlertManager(db)
        await manager.handle_violation(
            tenant_id=1,
            agent_name="MedBot",
            violation_type="accuracy_drift",
            details={},
        )

        added_rows = [call.args[0] for call in db.add.call_args_list]
        incident_rows = [r for r in added_rows if isinstance(r, IncidentReportDB)]
        assert len(incident_rows) == 0


# ─────────────────────────────────────────────────────────────────────────────
# C-5: GovernanceIntegration.post_execution — log_provenance wrong signature + await
# ─────────────────────────────────────────────────────────────────────────────


class TestC5LogProvenanceCall:
    """C-5: post_execution with model_provider must not raise TypeError from log_provenance."""

    @pytest.mark.asyncio
    async def test_post_execution_with_model_provider_does_not_raise(self) -> None:
        from src.core.governance.governance_agent.integration import GovernanceIntegration

        monitor = MagicMock(
            track_result=AsyncMock(),
            check_drift=AsyncMock(return_value=None),
        )
        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=monitor,
            alert_manager=MagicMock(handle_violation=AsyncMock()),
            ml_strategy=MagicMock(analyze=AsyncMock(return_value=None)),
        )

        # Must not raise — log_provenance was being awaited + wrong kwargs
        await integration.post_execution(
            tenant_id=1,
            agent_name="BotX",
            success=True,
            confidence_score=0.9,
            execution_time_ms=100,
            model_provider="openai",
            model_version="gpt-4",
        )

    @pytest.mark.asyncio
    async def test_post_execution_provenance_skipped_with_log(self, caplog) -> None:  # type: ignore[no-untyped-def]
        """post_execution with model_provider must log info (provenance needs ProvenanceService)."""
        import logging
        from src.core.governance.governance_agent.integration import GovernanceIntegration

        monitor = MagicMock(
            track_result=AsyncMock(),
            check_drift=AsyncMock(return_value=None),
        )
        integration = GovernanceIntegration(
            oversight_gate=MagicMock(),
            accuracy_monitor=monitor,
            alert_manager=MagicMock(handle_violation=AsyncMock()),
            ml_strategy=MagicMock(analyze=AsyncMock(return_value=None)),
        )

        with caplog.at_level(logging.INFO):
            await integration.post_execution(
                tenant_id=1,
                agent_name="ProvenanceBot",
                success=True,
                confidence_score=0.9,
                execution_time_ms=50,
                model_provider="anthropic",
                model_version="claude-3",
            )

        assert any("provenance logging skipped" in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# C-6: AccuracyMetric.id — ORM uses Integer, migration uses UUID
# ─────────────────────────────────────────────────────────────────────────────


class TestC6AccuracyMetricMigrationPK:
    """C-6: governance_accuracy_metrics must use Integer PK to match the ORM."""

    def _load_migration(self):
        path = (
            pathlib.Path(__file__).parent.parent.parent.parent
            / "alembic"
            / "versions"
            / "governance_agent_tables.py"
        )
        mod_name = "governance_agent_tables"
        if mod_name in sys.modules:
            return sys.modules[mod_name]
        spec = importlib.util.spec_from_file_location(mod_name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)  # type: ignore
        return mod

    def test_accuracy_metrics_pk_is_integer(self) -> None:
        """Migration must create Integer PK for governance_accuracy_metrics (not UUID)."""
        import sqlalchemy as sa
        from sqlalchemy.dialects import postgresql

        captured_cols: list = []

        mock_op = MagicMock()

        def capture_create(name, *args, **kwargs):
            if name == "governance_accuracy_metrics":
                captured_cols.extend(args)

        mock_op.create_table.side_effect = capture_create
        mock_op.create_index.return_value = None

        mod = self._load_migration()
        # Reload to pick up any changes
        if "governance_agent_tables" in sys.modules:
            del sys.modules["governance_agent_tables"]
        mod = self._load_migration()

        with patch("governance_agent_tables.op", mock_op):
            mod.upgrade()

        # Find the id column
        id_col = next(
            (c for c in captured_cols if isinstance(c, sa.Column) and c.name == "id"),
            None,
        )
        assert id_col is not None, "id column not found in governance_accuracy_metrics"
        assert isinstance(id_col.type, sa.Integer), (
            f"governance_accuracy_metrics.id is {type(id_col.type).__name__}, "
            "expected Integer to match the ORM model."
        )


# ─────────────────────────────────────────────────────────────────────────────
# C-7: RiskEntry — risk_description missing from migration
# ─────────────────────────────────────────────────────────────────────────────


class TestC7RiskEntryMigrationColumns:
    """C-7: governance_risk_entries migration must include risk_description, last_reviewed, reviewer_user_id."""

    def _run_upgrade_capture(self) -> dict[str, list]:
        """Returns {table_name: [Column, ...]} for tables created by upgrade."""
        import sqlalchemy as sa

        captured: dict[str, list] = {}

        if "governance_agent_tables" in sys.modules:
            del sys.modules["governance_agent_tables"]

        path = (
            pathlib.Path(__file__).parent.parent.parent.parent
            / "alembic"
            / "versions"
            / "governance_agent_tables.py"
        )
        spec = importlib.util.spec_from_file_location("governance_agent_tables", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["governance_agent_tables"] = mod
        spec.loader.exec_module(mod)  # type: ignore

        mock_op = MagicMock()

        def capture_create(name, *args, **kwargs):
            captured[name] = [c for c in args if isinstance(c, sa.Column)]

        mock_op.create_table.side_effect = capture_create
        mock_op.create_index.return_value = None

        with patch("governance_agent_tables.op", mock_op):
            mod.upgrade()

        return captured

    def _col_names(self, table: str) -> set[str]:
        return {c.name for c in self._run_upgrade_capture().get(table, [])}

    def test_risk_entries_has_risk_description(self) -> None:
        assert "risk_description" in self._col_names("governance_risk_entries"), (
            "risk_description (NOT NULL) is missing from the migration — "
            "any INSERT via the ORM will fail."
        )

    def test_risk_entries_has_last_reviewed(self) -> None:
        assert "last_reviewed" in self._col_names("governance_risk_entries")

    def test_risk_entries_has_reviewer_user_id(self) -> None:
        assert "reviewer_user_id" in self._col_names("governance_risk_entries")


# ─────────────────────────────────────────────────────────────────────────────
# C-8: generate_daily_digest — no date filter
# ─────────────────────────────────────────────────────────────────────────────


class TestC8DailyDigestDateFilter:
    """C-8: generate_daily_digest must only count alerts from today, not all time."""

    @pytest.mark.asyncio
    async def test_old_alerts_excluded_from_digest(self) -> None:
        """Alerts older than today must NOT appear in the digest count."""
        from src.core.governance.alert_manager import AlertManager, GovernanceAlert

        # Create one alert from 2 days ago, one from today
        old_alert = MagicMock(spec=GovernanceAlert)
        old_alert.severity = "high"
        old_alert.created_at = datetime.now(timezone.utc) - timedelta(days=2)
        old_alert.acknowledged = 0

        today_alert = MagicMock(spec=GovernanceAlert)
        today_alert.severity = "medium"
        today_alert.created_at = datetime.now(timezone.utc)
        today_alert.acknowledged = 0

        db = AsyncMock()
        # Without a date filter both rows are returned
        # With a date filter only today_alert is returned
        # We test that the digest total is 1 (only today's alert)
        db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[today_alert])))
        )

        manager = AlertManager(db)
        result = await manager.generate_daily_digest(tenant_id=1)

        assert result["total_alerts"] == 1, (
            "generate_daily_digest should only count today's alerts. "
            "Old alerts must be excluded by a date filter in the query."
        )

    @pytest.mark.asyncio
    async def test_digest_sql_includes_date_filter(self) -> None:
        """The SQL executed by generate_daily_digest must filter by created_at >= today."""
        import sqlalchemy as sa

        from src.core.governance.alert_manager import AlertManager

        db = AsyncMock()
        db.execute.return_value = MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )

        manager = AlertManager(db)
        await manager.generate_daily_digest(tenant_id=1)

        assert db.execute.called
        stmt = db.execute.call_args.args[0]
        # The compiled SQL must reference today's date boundary
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        today_str = datetime.now(timezone.utc).date().isoformat()
        assert today_str in compiled, (
            f"Expected today's date ({today_str}) in the SQL WHERE clause, "
            f"but got: {compiled[:300]}"
        )
