"""Tests for SP-WE-21 / NEW-WIRE-004: ProactiveScheduler dependency wiring.

Verifies that _init_proactive_deps() and the new _wire_proactive_extras()
helper set all 9 app.state attributes that _init_proactive_scheduler() reads.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.unit]


def _make_app_with_state() -> MagicMock:
    """Build a minimal FastAPI-like mock with a fresh app.state namespace."""

    class _State:
        pass

    app = MagicMock()
    app.state = _State()
    return app


class TestWireProactiveExtras:
    """SP-WE-21: _wire_proactive_extras() must set all 7 missing app.state deps."""

    def test_function_exists_and_importable(self) -> None:
        """_wire_proactive_extras() must be importable from app_lifespan."""
        from src.core.app_lifespan import _wire_proactive_extras

        assert callable(_wire_proactive_extras)

    def test_health_registry_set(self) -> None:
        from src.core.app_lifespan import _wire_proactive_extras

        app = _make_app_with_state()
        _wire_proactive_extras(app, session_factory=MagicMock())
        assert getattr(app.state, "health_registry", None) is not None

    def test_failover_provider_set(self) -> None:
        from src.core.app_lifespan import _wire_proactive_extras

        app = _make_app_with_state()
        _wire_proactive_extras(app, session_factory=MagicMock())
        assert getattr(app.state, "failover_provider", None) is not None

    def test_prometheus_client_set(self) -> None:
        from src.core.app_lifespan import _wire_proactive_extras

        app = _make_app_with_state()
        _wire_proactive_extras(app, session_factory=MagicMock())
        assert getattr(app.state, "prometheus_client", None) is not None

    def test_consent_repo_set(self) -> None:
        from src.core.app_lifespan import _wire_proactive_extras

        app = _make_app_with_state()
        _wire_proactive_extras(app, session_factory=MagicMock())
        assert getattr(app.state, "consent_repo", None) is not None

    def test_audit_repo_set(self) -> None:
        from src.core.app_lifespan import _wire_proactive_extras

        app = _make_app_with_state()
        _wire_proactive_extras(app, session_factory=MagicMock())
        assert getattr(app.state, "audit_repo", None) is not None

    def test_role_repo_set(self) -> None:
        from src.core.app_lifespan import _wire_proactive_extras

        app = _make_app_with_state()
        _wire_proactive_extras(app, session_factory=MagicMock())
        assert getattr(app.state, "role_repo", None) is not None

    def test_workflow_repo_set(self) -> None:
        from src.core.app_lifespan import _wire_proactive_extras

        app = _make_app_with_state()
        _wire_proactive_extras(app, session_factory=MagicMock())
        assert getattr(app.state, "workflow_repo", None) is not None

    def test_pii_scanner_set(self) -> None:
        from src.core.app_lifespan import _wire_proactive_extras

        app = _make_app_with_state()
        _wire_proactive_extras(app, session_factory=MagicMock())
        assert getattr(app.state, "pii_scanner", None) is not None

    def test_dpia_repo_set(self) -> None:
        from src.core.app_lifespan import _wire_proactive_extras

        app = _make_app_with_state()
        _wire_proactive_extras(app, session_factory=MagicMock())
        assert getattr(app.state, "dpia_repo", None) is not None

    def test_does_not_overwrite_preexisting_state(self) -> None:
        """If SP-WE-18 already set health_registry, do not overwrite it."""
        from src.core.app_lifespan import _wire_proactive_extras

        app = _make_app_with_state()
        sentinel = object()
        app.state.health_registry = sentinel
        _wire_proactive_extras(app, session_factory=MagicMock())
        assert app.state.health_registry is sentinel


class TestStubReposProtocolCompliance:
    """Stubs must satisfy the Protocols the monitors expect."""

    @pytest.mark.asyncio
    async def test_consent_stub_returns_empty(self) -> None:
        from src.core.copilot.proactive.stub_repos import StubConsentRepo

        repo = StubConsentRepo(session_factory=MagicMock())
        result = await repo.list_users_with_expiring_consent(tenant_id=1, days_before_expiry=7)
        assert result == []

    @pytest.mark.asyncio
    async def test_audit_stub_returns_empty(self) -> None:
        from src.core.copilot.proactive.stub_repos import StubAuditRepo

        repo = StubAuditRepo(session_factory=MagicMock())
        result = await repo.count_permission_denied_per_user(tenant_id=1, hours=24)
        assert result == []

    @pytest.mark.asyncio
    async def test_role_stub_returns_false(self) -> None:
        from datetime import datetime, timezone

        from src.core.copilot.proactive.stub_repos import StubRoleRepo

        repo = StubRoleRepo(session_factory=MagicMock())
        result = await repo.was_any_role_created_after(
            tenant_id=1, after=datetime.now(timezone.utc)
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_workflow_stub_returns_empty(self) -> None:
        from src.core.copilot.proactive.stub_repos import StubWorkflowRepo

        repo = StubWorkflowRepo(session_factory=MagicMock())
        result = await repo.list_active(tenant_id=1)
        assert result == []

    @pytest.mark.asyncio
    async def test_dpia_stub_returns_false(self) -> None:
        from src.core.copilot.proactive.stub_repos import StubDPIARepo

        repo = StubDPIARepo(session_factory=MagicMock())
        result = await repo.exists_for_workflow(tenant_id=1, workflow_id="wf-1")
        assert result is False

    def test_pii_scanner_stub_returns_empty(self) -> None:
        from src.core.copilot.proactive.stub_repos import StubWorkflowPIIScanner

        scanner = StubWorkflowPIIScanner()
        assert scanner.scan({"some": "config"}) == []

    @pytest.mark.asyncio
    async def test_prometheus_stub_returns_zero(self) -> None:
        from src.core.copilot.proactive.stub_repos import StubPrometheusClient

        prom = StubPrometheusClient()
        assert await prom.list_workflows(tenant_id=1) == []
        assert await prom.execution_count("wf", 1, "1h") == 0
        assert await prom.get_histogram_p95("m", {}, "1h") == 0.0
        assert await prom.get_counter_sum("m", {}, "1h") == 0.0
        assert await prom.get_counter_average("m", {}, "1d", "1h") == 0.0


class TestStartupOrdering:
    """_init_proactive_deps() must be invoked before _init_proactive_scheduler()."""

    def test_lifespan_calls_deps_before_scheduler(self) -> None:
        """Static-source check that deps is wired before scheduler in app_lifespan.py.

        After SP-WE-21 refactoring, init steps use a lambda wrapper in init_steps list
        instead of direct await calls. Check for the step name in the init list ordering.
        """
        from pathlib import Path

        src = Path("src/core/app_lifespan.py").read_text(encoding="utf-8")
        # Support both direct call and lambda wrapper pattern
        idx_deps = max(
            src.find("await _init_proactive_deps(app)"),
            src.find('"_init_proactive_deps"'),  # lambda wrapper in init_steps list
        )
        idx_sched = max(
            src.find("await _init_proactive_scheduler(app)"),
            src.find('"_init_proactive_scheduler"'),
        )
        assert idx_deps != -1, "_init_proactive_deps call missing"
        assert idx_sched != -1, "_init_proactive_scheduler call missing"
        assert idx_deps < idx_sched, "deps must be invoked before scheduler"
