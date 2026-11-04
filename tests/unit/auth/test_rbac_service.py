"""
Tests for src/core/auth/rbac_service.py (DEPRECATED WRAPPER)
Target: 85%+ coverage
Tests: 30-40
"""

import warnings
from unittest.mock import MagicMock, patch

import pytest


class TestRBACServiceWrapperImport:
    """Test imports work (backward compatibility)"""

    def test_import_rbac_service_class(self):
        """Test RBACService class import works"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.auth.rbac_service import RBACService

        assert RBACService is not None

    def test_import_permission(self):
        """Test Permission import works"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.auth.rbac_service import Permission

        assert Permission is not None

    def test_import_get_rbac_service(self):
        """Test get_rbac_service function import works"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.auth.rbac_service import get_rbac_service

        assert get_rbac_service is not None

    def test_import_rbac_service_protocol(self):
        """Test RBACServiceProtocol import works"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.auth.rbac_service import RBACServiceProtocol

        assert RBACServiceProtocol is not None

    def test_import_logger(self):
        """Test logger import works"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.auth.rbac_service import logger

        assert logger is not None


class TestRBACServiceWrapperDeprecation:
    """Test deprecation warning for RBACService wrapper"""

    def test_module_imports_without_error(self):
        """Test that module can be imported without error"""
        # Import should work without raising exceptions
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.auth.rbac_service import RBACService

    def test_deprecation_warning_emitted(self):
        """Test that deprecation warning is emitted on import.

        Het weggooien uit `sys.modules` is hier noodzakelijk -- de waarschuwing vuurt alleen bij
        een VERSE import. Maar het moet in een `finally` worden teruggedraaid naar het
        OORSPRONKELIJKE moduleobject, en dat gebeurde niet.

        Zonder dat herstel houdt elke module die er al een klasse uit had geimporteerd een
        verwijzing naar de oude objecten, terwijl een latere importeur nieuwe maakt. Een
        `isinstance` in een volstrekt ander testbestand faalt dan zonder zichtbare reden, en
        alleen wanneer de volgorde die twee bij elkaar zet. Dat is de vorm van ADR-036 OP-45; het
        `tests/conftest.py`-vangnet betrapte deze test daarop op 2026-08-11.
        """
        import sys

        naam = "src.core.auth.rbac_service"
        origineel = sys.modules.get(naam)
        sys.modules.pop(naam, None)
        try:
            with pytest.warns(DeprecationWarning, match="core.auth.rbac_service is deprecated"):
                from src.core.auth.rbac_service import RBACService  # noqa: F401
        finally:
            if origineel is not None:
                sys.modules[naam] = origineel
            else:
                sys.modules.pop(naam, None)

    def test_get_rbac_service_function_works(self):
        """Test get_rbac_service function works through wrapper"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.auth.rbac_service import get_rbac_service

        # Verify the function exists and is callable
        assert callable(get_rbac_service)

        # Test that it returns an RBACService instance
        with patch("src.core.services.rbac_service.get_db_session"):
            import asyncio

            service = asyncio.run(get_rbac_service())
            from src.core.services.rbac_service import RBACService as RealRBACService

            assert isinstance(service, RealRBACService)


class TestRBACServiceWrapperExports:
    """Test all expected exports are available"""

    def test_all_exports_available(self):
        """Test all expected exports are available in __all__"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.auth.rbac_service import (
                Permission,
                RBACService,
                RBACServiceProtocol,
                get_rbac_service,
                logger,
            )

        # All should be importable
        assert RBACService is not None
        assert Permission is not None
        assert get_rbac_service is not None
        assert RBACServiceProtocol is not None
        assert logger is not None

    def test_all_exports_in_dunder_all(self):
        """Test all exports are listed in __all__"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.auth.rbac_service import __all__

        expected_exports = [
            "RBACService",
            "Permission",
            "ResourceOwnershipChecker",
            "get_rbac_service",
            "RBACServiceProtocol",
            "logger",
        ]
        for export in expected_exports:
            assert export in __all__, f"{export} not found in __all__"
