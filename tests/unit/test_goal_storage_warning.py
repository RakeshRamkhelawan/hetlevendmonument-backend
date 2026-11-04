"""
Happy path:    In-memory storage is uitgeschakeld in productie (feature flag)
Unhappy path:  In production zonder flag: endpoint geeft 503 met duidelijke fout
Behavioral:    Ontwikkelaar ziet duidelijke deprecation warning bij startup
"""

import os

import pytest


class TestGoalStorageProductionGuard:
    def test_happy_path_dev_mode_allowed(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("ENABLE_INMEMORY_GOALS", "true")
        import importlib

        import src.core.api.goal_endpoints as mod

        importlib.reload(mod)

    def test_unhappy_path_production_without_flag_raises(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("ENABLE_INMEMORY_GOALS", raising=False)
        import importlib

        from fastapi import HTTPException

        import src.core.api.goal_endpoints as mod

        importlib.reload(mod)

        with pytest.raises(HTTPException) as exc_info:
            mod._check_production_guard()
        assert exc_info.value.status_code == 503
        assert "productie" in exc_info.value.detail.lower()

    def test_behavioral_startup_logs_warning(self, monkeypatch, caplog):
        import logging

        monkeypatch.setenv("ENVIRONMENT", "development")
        with caplog.at_level(logging.WARNING):
            import importlib

            import src.core.api.goal_endpoints as mod

            importlib.reload(mod)
        assert any("in-memory" in r.message.lower() for r in caplog.records)
