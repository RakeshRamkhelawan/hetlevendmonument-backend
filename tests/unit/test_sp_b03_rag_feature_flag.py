"""
SP-B03 (re-executed 2026-05-29): RAG endpoints gatten achter feature-flag.

RAG is post-MVP en vereist een vector store. De endpoints zijn stubs
en mogen niet live exposed zijn in productie zonder feature-flag.

Tests verifieren:
1. RAG_ENABLED is canoniek en default false
2. ENABLE_RAG_ROUTERS werkt als legacy fallback (met deprecation warning)
3. RAG_ENABLED heeft voorrang op legacy fallback
4. RAG routes zijn niet gemount bij disabled (404)
5. Specifiek /health en /collections geven 404 bij disabled
6. RAG routes zijn gemount bij enabled (backwards compat)
7. .env.example documenteert de flag
8. Behavioral: operator ziet 404 voor alle RAG routes by default
"""

import inspect
import os
import pathlib
import sys
import types
from unittest.mock import patch

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from src.core.api.registries.auth_admin import _rag_enabled as _resolve_rag_router_enabled
from src.core.api.registries.auth_admin import _register_rag_only as _register_admin_management

pytestmark = [pytest.mark.unit, pytest.mark.security]


class TestRAGFeatureFlagSource:
    """Statische checks op feature-flag contract."""

    def test_router_registry_contains_canonical_and_legacy_flags(self):
        """Broncode bevat zowel canonieke als legacy flagnamen (in auth_admin registry)."""
        import sys

        auth_admin = sys.modules["src.core.api.registries.auth_admin"]
        source = inspect.getsource(auth_admin)
        assert "RAG_ENABLED" in source
        assert "ENABLE_RAG_ROUTERS" in source


class TestRAGFlagResolution:
    """Resolver precedence en parsing."""

    def test_default_is_disabled_when_flags_unset(self):
        """Als geen van beide flags gezet is, blijft RAG uit."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RAG_ENABLED", None)
            os.environ.pop("ENABLE_RAG_ROUTERS", None)
            assert _resolve_rag_router_enabled() is False

    def test_canonical_flag_true_enables(self):
        """RAG_ENABLED=true schakelt RAG in."""
        with patch.dict(os.environ, {"RAG_ENABLED": "true"}, clear=False):
            assert _resolve_rag_router_enabled() is True

    def test_canonical_flag_numeric_one_enables(self):
        """RAG_ENABLED=1 schakelt RAG in (truthy parsering)."""
        with patch.dict(os.environ, {"RAG_ENABLED": "1"}, clear=False):
            assert _resolve_rag_router_enabled() is True

    def test_legacy_flag_used_only_as_fallback(self):
        """Legacy flag werkt zolang canonieke flag niet gezet is."""
        with patch.dict(os.environ, {"ENABLE_RAG_ROUTERS": "true"}, clear=False):
            os.environ.pop("RAG_ENABLED", None)
            assert _resolve_rag_router_enabled() is True

    def test_canonical_flag_has_precedence_over_legacy(self):
        """RAG_ENABLED=false wint van ENABLE_RAG_ROUTERS=true."""
        with patch.dict(
            os.environ,
            {"RAG_ENABLED": "false", "ENABLE_RAG_ROUTERS": "true"},
            clear=False,
        ):
            assert _resolve_rag_router_enabled() is False

    def test_legacy_flag_emits_deprecation_log(self):
        """ENABLE_RAG_ROUTERS geeft een deprecation warning via de logger."""
        with patch("src.core.api.registries.auth_admin.logger") as mock_logger:
            with patch.dict(os.environ, {"ENABLE_RAG_ROUTERS": "true"}, clear=False):
                os.environ.pop("RAG_ENABLED", None)
                _resolve_rag_router_enabled()
        mock_logger.warning.assert_called_once()
        call_msg = mock_logger.warning.call_args[0][0]
        assert "ENABLE_RAG_ROUTERS" in call_msg
        assert "deprecated" in call_msg


class TestRAGRouterRegistration:
    """Behavior van router mounting op een geïsoleerde app."""

    def test_rag_routes_not_registered_when_disabled(self):
        """Bij disabled worden er geen /api/v1/rag routes gemount."""
        with patch.dict(os.environ, {"RAG_ENABLED": "false"}, clear=False):
            app = FastAPI()
            registered = _register_admin_management(app)
            paths = [route.path for route in app.routes if hasattr(route, "path")]
            rag_paths = [path for path in paths if "/rag" in path]

            assert registered == 0
            assert rag_paths == []

            client = TestClient(app)
            response = client.get("/api/v1/rag/health")
            assert response.status_code == 404

    def test_rag_health_returns_404_when_disabled(self):
        """/api/v1/rag/health geeft 404 als RAG_ENABLED=false."""
        with patch.dict(os.environ, {"RAG_ENABLED": "false"}, clear=False):
            app = FastAPI()
            _register_admin_management(app)
            client = TestClient(app)
            assert client.get("/api/v1/rag/health").status_code == 404

    def test_rag_collections_returns_404_when_disabled(self):
        """/api/v1/rag/collections geeft 404 als RAG_ENABLED=false."""
        with patch.dict(os.environ, {"RAG_ENABLED": "false"}, clear=False):
            app = FastAPI()
            _register_admin_management(app)
            client = TestClient(app)
            assert client.get("/api/v1/rag/collections").status_code == 404

    def test_rag_routes_registered_when_enabled(self):
        """Bij enabled wordt de RAG router wel gemount."""
        stub_module = types.ModuleType("src.core.api.rag_endpoints")
        stub_router = APIRouter(prefix="/api/v1/rag")

        @stub_router.get("/health")
        async def _health() -> dict[str, str]:
            return {"status": "ok"}

        stub_module.router = stub_router

        with (
            patch.dict(
                os.environ,
                {"RAG_ENABLED": "true"},
                clear=False,
            ),
            patch.dict(
                sys.modules,
                {"src.core.api.rag_endpoints": stub_module},
                clear=False,
            ),
        ):
            app = FastAPI()
            registered = _register_admin_management(app)
            paths = [route.path for route in app.routes if hasattr(route, "path")]
            rag_paths = [path for path in paths if path.startswith("/api/v1/rag")]

            assert registered == 1
            assert "/api/v1/rag/health" in rag_paths

            client = TestClient(app)
            response = client.get("/api/v1/rag/health")
            assert response.status_code == 200


class TestRAGBehavioral:
    """Behavioral tests vanuit operator-perspectief."""

    def test_operator_cannot_access_rag_without_flag(self):
        """Operator die deployt zonder RAG_ENABLED ziet 404 op alle RAG routes."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RAG_ENABLED", None)
            os.environ.pop("ENABLE_RAG_ROUTERS", None)
            app = FastAPI()
            _register_admin_management(app)
            client = TestClient(app)
            for path in ["/api/v1/rag/health", "/api/v1/rag/collections"]:
                r = client.get(path)
                assert r.status_code == 404, (
                    f"{path} gaf {r.status_code} zonder RAG_ENABLED, verwacht 404"
                )


class TestEnvConfiguration:
    """Documentatie en default contract."""

    def test_env_example_contains_rag_enabled(self):
        """.env.example documenteert de canonieke flag."""
        env_example_path = pathlib.Path(__file__).parents[2] / ".env.example"
        try:
            content = env_example_path.read_text(encoding="utf-8")
            assert "RAG_ENABLED" in content
        except FileNotFoundError:
            pytest.skip(".env.example niet gevonden")
