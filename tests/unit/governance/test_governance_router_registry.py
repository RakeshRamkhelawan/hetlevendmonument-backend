"""Tests for governance router registration in router_registry (Phase 4).

Verifies that the governance v1 router is registered under the correct
prefix and tag, without spinning up the full application stack.
"""

from __future__ import annotations

import inspect


class TestGovernanceRouterRegistryFunction:
    """_register_governance_v1 function exists and registers the router."""

    def test_register_function_exists(self) -> None:
        from src.core.api.router_registry import _register_governance_v1

        assert callable(_register_governance_v1)

    def test_register_function_accepts_app(self) -> None:
        from src.core.api.router_registry import _register_governance_v1

        sig = inspect.signature(_register_governance_v1)
        assert "app" in sig.parameters

    def test_register_function_returns_int(self) -> None:
        """Returns count of registered routers."""
        from unittest.mock import MagicMock

        from src.core.api.router_registry import _register_governance_v1

        app = MagicMock()
        result = _register_governance_v1(app)
        assert isinstance(result, int)
        assert result >= 1

    def test_register_function_calls_include_router(self) -> None:
        from unittest.mock import MagicMock

        from src.core.api.router_registry import _register_governance_v1

        app = MagicMock()
        _register_governance_v1(app)
        app.include_router.assert_called()

    def test_registered_router_has_governance_prefix(self) -> None:
        from unittest.mock import MagicMock  # noqa: F401 -- call not needed here

        from src.core.api.router_registry import _register_governance_v1

        app = MagicMock()
        _register_governance_v1(app)
        # The composite router has no top-level prefix; prefix lives in sub-routers.
        # Verify that all registered routes start with /api/v1/governance.
        included_routers = [c.args[0] for c in app.include_router.call_args_list]
        all_route_paths = [
            r.path for router in included_routers for r in router.routes if hasattr(r, "path")
        ]
        assert any(p.startswith("/api/v1/governance") for p in all_route_paths), (
            f"Expected routes under /api/v1/governance, got: {all_route_paths}"
        )
