"""
Happy path:    Terminal werkt in development als FEATURE_FLAG_TERMINAL=true
Unhappy path:  In production zonder flag geeft endpoint 403
Behavioral:    Foutbericht legt uit dat terminal uitgeschakeld is in productie
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


class TestTerminalProductionGuard:
    """Test production guard for terminal endpoint."""

    def test_happy_path_enabled_in_dev(self):
        """Terminal should work in development when enabled."""
        # Import fresh with patched env vars
        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "development", "FEATURE_FLAG_TERMINAL_ENABLED": "true"},
        ):
            # Reload the module to pick up new env vars
            import importlib

            terminal_router = importlib.import_module("src.core.api.v1.terminal.router")

            importlib.reload(terminal_router)

            # Guard should not raise in dev
            try:
                terminal_router._require_terminal_enabled()
            except HTTPException as e:
                pytest.fail(f"Guard should not raise in dev mode, got: {e}")

    def test_unhappy_path_blocked_in_production(self):
        """Terminal should be blocked in production without flag."""
        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "production"},
            clear=True,  # Clear FEATURE_FLAG_TERMINAL_ENABLED
        ):
            import importlib

            # Must reload dependencies.py first (module-level _ENVIRONMENT var)
            terminal_deps = importlib.import_module("src.core.api.v1.terminal.dependencies")
            importlib.reload(terminal_deps)
            terminal_router = importlib.import_module("src.core.api.v1.terminal.router")
            importlib.reload(terminal_router)

            # Guard should raise 403 in production
            with pytest.raises(HTTPException) as exc_info:
                terminal_router._require_terminal_enabled()

            assert exc_info.value.status_code == 403

    def test_behavioral_error_message_explains_why(self):
        """Error message should explain why terminal is disabled."""
        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "production"},
            clear=True,  # Clear FEATURE_FLAG_TERMINAL_ENABLED
        ):
            import importlib

            terminal_router = importlib.import_module("src.core.api.v1.terminal.router")

            importlib.reload(terminal_router)

            # Guard should raise 403 with explanatory message
            with pytest.raises(HTTPException) as exc_info:
                terminal_router._require_terminal_enabled()

            assert exc_info.value.status_code == 403
            detail = exc_info.value.detail.lower()
            assert "terminal" in detail or "disabled" in detail or "production" in detail, (
                f"Expected 'terminal', 'disabled', or 'production' in error message, got: {detail}"
            )
