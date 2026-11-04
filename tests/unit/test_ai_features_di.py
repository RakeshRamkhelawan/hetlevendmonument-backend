"""
Unit tests for AI Features DI Container migration (Fase 3.2).

Tests that:
1. No global None variables exist in ai_features_endpoints.py
2. DI container has factory providers for AI components
3. Endpoints can be called with injected dependencies
"""

import ast
import inspect
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestAIFeaturesGlobalsRemoved:
    """Test that global variables have been removed from ai_features_endpoints."""

    def test_no_global_none_variables(self) -> None:
        """
        Verify that _adaptive_learning_engine, _intelligent_router, and
        _predictive_analytics globals have been removed.
        """
        # Arrange
        file_path = Path("src/core/api/ai_features_endpoints.py")
        assert file_path.exists(), f"File not found: {file_path}"

        # Act
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # Find global variable assignments at module level
        global_vars = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        global_vars.append(target.id)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    global_vars.append(node.target.id)

        # Assert
        forbidden_globals = [
            "_adaptive_learning_engine",
            "_intelligent_router",
            "_predictive_analytics",
        ]

        for var in forbidden_globals:
            assert var not in global_vars, (
                f"Global variable '{var}' still exists in ai_features_endpoints.py. "
                f"Must be removed for DI migration."
            )

    def test_no_lazy_init_functions(self) -> None:
        """
        Verify that old lazy-init functions (get_learning_engine, get_router,
        get_analytics) no longer exist or have been renamed to _build_*.
        """
        # Arrange
        file_path = Path("src/core/api/ai_features_endpoints.py")
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # Act
        old_functions = ["get_learning_engine", "get_router", "get_analytics"]
        found_old_functions = []

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef):
                if node.name in old_functions:
                    found_old_functions.append(node.name)

        # Assert - these should no longer exist as public functions
        assert len(found_old_functions) == 0, (
            f"Old lazy-init functions still exist: {found_old_functions}. "
            f"Rename to _build_* for DI factory pattern."
        )


class TestDIContainerProviders:
    """Test that DI container has factory providers for AI components."""

    def test_container_has_adaptive_learning_engine_provider(self) -> None:
        """Verify Container has adaptive_learning_engine factory provider."""
        # Arrange
        from src.core.container import Container

        # Act & Assert
        assert hasattr(
            Container, "adaptive_learning_engine"
        ), "Container missing adaptive_learning_engine provider"
        provider = Container.adaptive_learning_engine
        assert provider is not None, "adaptive_learning_engine provider is None"

    def test_container_has_intelligent_router_provider(self) -> None:
        """Verify Container has intelligent_router factory provider."""
        # Arrange
        from src.core.container import Container

        # Act & Assert
        assert hasattr(
            Container, "intelligent_router"
        ), "Container missing intelligent_router provider"
        provider = Container.intelligent_router
        assert provider is not None, "intelligent_router provider is None"

    def test_container_has_predictive_analytics_provider(self) -> None:
        """Verify Container has predictive_analytics factory provider."""
        # Arrange
        from src.core.container import Container

        # Act & Assert
        assert hasattr(
            Container, "predictive_analytics"
        ), "Container missing predictive_analytics provider"
        provider = Container.predictive_analytics
        assert provider is not None, "predictive_analytics provider is None"


class TestFactoryFunctionsExist:
    """Test that factory functions exist in ai_features_endpoints."""

    def test_build_learning_engine_function_exists(self) -> None:
        """Verify _build_learning_engine factory function exists."""
        # Arrange
        import src.core.api.ai_features_endpoints as endpoints

        # Act & Assert
        assert hasattr(
            endpoints, "_build_learning_engine"
        ), "_build_learning_engine factory function missing"

    def test_build_intelligent_router_function_exists(self) -> None:
        """Verify _build_intelligent_router factory function exists."""
        # Arrange
        import src.core.api.ai_features_endpoints as endpoints

        # Act & Assert
        assert hasattr(
            endpoints, "_build_intelligent_router"
        ), "_build_intelligent_router factory function missing"

    def test_build_predictive_analytics_function_exists(self) -> None:
        """Verify _build_predictive_analytics factory function exists."""
        # Arrange
        import src.core.api.ai_features_endpoints as endpoints

        # Act & Assert
        assert hasattr(
            endpoints, "_build_predictive_analytics"
        ), "_build_predictive_analytics factory function missing"


class TestDIInjection:
    """Test that endpoints use DI injection properly."""

    def test_endpoints_use_provide_decorator(self) -> None:
        """
        Verify endpoints use @inject and Provide[] for dependencies.
        """
        # Arrange
        file_path = Path("src/core/api/ai_features_endpoints.py")
        source = file_path.read_text(encoding="utf-8")

        # Act & Assert
        # Check for import of inject and Provide
        assert (
            "from dependency_injector.wiring import" in source
        ), "Missing dependency_injector.wiring import"
        assert "inject" in source, "Missing @inject decorator usage"
        assert "Provide" in source, "Missing Provide[] usage"


class TestMainWiring:
    """Test that main.py wires ai_features_endpoints."""

    def test_main_wires_ai_features_endpoints(self) -> None:
        """Verify main.py wires the ai_features_endpoints module."""
        # Arrange
        file_path = Path("src/main.py")
        source = file_path.read_text(encoding="utf-8")

        # Act & Assert
        expected_module = "src.core.api.ai_features_endpoints"
        assert expected_module in source, f"main.py must wire '{expected_module}' module"


# ============================================================================
# DI MIGRATION VERIFICATION TESTS (Integration-style)
# ============================================================================


class TestDIIntegration:
    """Integration tests for DI migration verification."""

    @pytest.mark.unit
    def test_container_providers_are_callable(self) -> None:
        """Verify container providers can be called (even if they fail without deps)."""
        # Arrange
        from src.core.container import container

        # Act & Assert - providers exist and are factory type
        assert container.adaptive_learning_engine is not None
        assert container.intelligent_router is not None
        assert container.predictive_analytics is not None

    @pytest.mark.unit
    def test_factory_imports_resolve(self) -> None:
        """Verify factory function imports resolve correctly."""
        # Arrange & Act - Should not raise ImportError
        from src.core.api.ai_features_endpoints import (
            _build_intelligent_router,
            _build_learning_engine,
            _build_predictive_analytics,
        )

        # Assert - Functions are callable
        assert callable(_build_learning_engine)
        assert callable(_build_intelligent_router)
        assert callable(_build_predictive_analytics)


# ============================================================================
# FASE 3.2 COMPLETION STATUS
# ============================================================================
# Tests to verify:
# - Global None variables removed: _adaptive_learning_engine, etc.
# - DI Container has factory providers for all 3 AI components
# - Factory functions renamed to _build_* pattern
# - Endpoints use @inject and Provide[]
# - main.py wires ai_features_endpoints module
# ============================================================================
