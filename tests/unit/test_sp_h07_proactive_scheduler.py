"""SP-H07: ProactiveScheduler wiring in app_lifespan.

Bug B-026: ProactiveScheduler was never instantiated or started in app_lifespan.py.
"""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.unit
class TestProactiveSchedulerWiring:
    def test_app_lifespan_imports_proactive_scheduler(self) -> None:
        """app_lifespan.py imports ProactiveScheduler at module or function level."""
        import pathlib

        source = pathlib.Path("src/core/app_lifespan.py").read_text(encoding="utf-8")
        assert "ProactiveScheduler" in source, (
            "ProactiveScheduler wordt niet geimporteerd/gestart in app_lifespan (B-026)"
        )

    def test_app_lifespan_has_init_proactive_scheduler(self) -> None:
        """app_lifespan.py defines an async init function for the scheduler."""
        from src.core import app_lifespan

        assert hasattr(app_lifespan, "_init_proactive_scheduler"), (
            "_init_proactive_scheduler ontbreekt in app_lifespan"
        )
        sig = inspect.signature(app_lifespan._init_proactive_scheduler)
        assert "app" in sig.parameters, "_init_proactive_scheduler moet een 'app' parameter hebben"

    def test_app_lifespan_has_cleanup_proactive_scheduler(self) -> None:
        """app_lifespan.py defines a cleanup function for graceful shutdown."""
        from src.core import app_lifespan

        assert hasattr(app_lifespan, "_cleanup_proactive_scheduler"), (
            "_cleanup_proactive_scheduler ontbreekt in app_lifespan"
        )

    def test_startup_phase_calls_init_proactive_scheduler(self) -> None:
        """The lifespan startup sequence calls _init_proactive_scheduler."""
        import pathlib

        source = pathlib.Path("src/core/app_lifespan.py").read_text(encoding="utf-8")
        assert "_init_proactive_scheduler(app)" in source, (
            "_init_proactive_scheduler(app) wordt niet aangeroepen in startup phase"
        )

    def test_shutdown_phase_calls_cleanup_proactive_scheduler(self) -> None:
        """The lifespan shutdown sequence calls _cleanup_proactive_scheduler."""
        import pathlib

        source = pathlib.Path("src/core/app_lifespan.py").read_text(encoding="utf-8")
        assert "_cleanup_proactive_scheduler" in source, (
            "_cleanup_proactive_scheduler wordt niet aangeroepen in shutdown phase"
        )
