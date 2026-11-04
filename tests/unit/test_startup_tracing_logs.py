"""
Test: Startup tracing logs in app_lifespan.py.
Verifies that each init step logs its duration.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
class TestStartupTracingLogs:
    """BE-UTL-007: app_lifespan must log timing for each init step."""

    @pytest.mark.asyncio
    async def test_lifespan_logs_startup_timing(self) -> None:
        from fastapi import FastAPI

        from src.core.app_lifespan import app_lifespan

        app = FastAPI()

        # Patch all _init_* functions to be instant no-ops
        init_names = [
            "_init_database",
            "_init_tenant_filtering",
            "_init_redis_services",
            "_init_feature_flags",
            "_seed_initial_data",
            "_seed_default_roles",
            "_init_event_system",
            "_init_twin_event_bridge",
            "_init_alert_notification_bridge",
            "_init_llm_service",
            "_init_agent_health_write_bridge",
            "_init_guna_router",
            "_init_council_cache_invalidator",
            "_init_proactive_deps",
            "_init_compliance_monitors",
            "_init_proactive_scheduler",
        ]

        mocks = {}
        for name in init_names:
            mocks[name] = patch(
                f"src.core.app_lifespan.{name}", new_callable=AsyncMock
            )

        # _init_database must return True
        mocks["_init_database"] = patch(
            "src.core.app_lifespan._init_database",
            new_callable=AsyncMock,
            return_value=True,
        )

        with patch("src.core.app_lifespan.configure_logging"):
            with patch("src.main.wire_container"):
                with patch("src.core.app_lifespan.close_database", new_callable=AsyncMock):
                    with patch("src.core.app_lifespan._cleanup_redis", new_callable=AsyncMock):
                        with patch("src.core.app_lifespan._cleanup_batch_manager", new_callable=AsyncMock):
                            with patch("src.core.app_lifespan._cleanup_twin_event_bridge", new_callable=AsyncMock):
                                with patch("src.core.app_lifespan._cleanup_tenant_factories", new_callable=AsyncMock):
                                    with patch("src.core.app_lifespan._cleanup_activepieces", new_callable=AsyncMock):
                                        with patch("src.core.app_lifespan._cleanup_event_consumer", new_callable=AsyncMock):
                                            with patch("src.core.app_lifespan._cleanup_event_publisher", new_callable=AsyncMock):
                                                with patch("src.core.app_lifespan._cleanup_proactive_scheduler", new_callable=AsyncMock):
                                                    with patch("src.core.app_lifespan._cleanup_guna_router", new_callable=AsyncMock):
                                                        # Enter all init mocks as context managers
                                                        cm_stack = []
                                                        for m in mocks.values():
                                                            cm_stack.append(m)
                                                        # Nested context manager entry
                                                        async def run_lifespan():
                                                            cm_exits = []
                                                            try:
                                                                for cm in cm_stack:
                                                                    val = cm.__enter__()
                                                                    cm_exits.append(cm)
                                                                gen = app_lifespan(app)
                                                                await gen.__aenter__()
                                                                await gen.__aexit__(None, None, None)
                                                            finally:
                                                                for cm in reversed(cm_exits):
                                                                    cm.__exit__(None, None, None)

                                                        with patch("src.core.app_lifespan.logger") as mock_logger:
                                                            await run_lifespan()

        # Verify timing logs were emitted
        log_calls = [str(c) for c in mock_logger.info.call_args_list]
        timing_logs = [c for c in log_calls if "[STARTUP]" in c]
        assert len(timing_logs) > 0, "No [STARTUP] timing logs found"

        # Verify total startup log
        total_logs = [c for c in log_calls if "total startup" in c]
        assert len(total_logs) > 0, "No 'total startup' log found"

    @pytest.mark.asyncio
    async def test_lifespan_logs_failed_step(self) -> None:
        """If an init step fails, the error must be logged with timing."""
        from fastapi import FastAPI

        from src.core.app_lifespan import app_lifespan

        app = FastAPI()

        with patch("src.core.app_lifespan._init_database", new_callable=AsyncMock, return_value=True):
            with patch("src.core.app_lifespan._init_tenant_filtering", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
                with patch("src.core.app_lifespan.configure_logging"):
                    with patch("src.main.wire_container"):
                        with patch("src.core.app_lifespan.logger") as mock_logger:
                            gen = app_lifespan(app)
                            try:
                                await gen.__aenter__()
                            except RuntimeError:
                                pass

        error_logs = [str(c) for c in mock_logger.error.call_args_list]
        failed_logs = [c for c in error_logs if "[STARTUP]" in c and "_init_tenant_filtering" in c and "failed" in c]
        assert len(failed_logs) > 0, "No error log for failed init step"
