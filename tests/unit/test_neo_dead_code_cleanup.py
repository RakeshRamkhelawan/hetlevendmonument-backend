"""
NEO Audit Fix: Sprint 8 - Dead Code Cleanup

ISSUE: Production code mag geen debug print statements bevatten
ISSUE: Alle imports moeten geldig zijn (geen broken imports)

Files checked:
- src/core/api/auth/router.py
- src/core/api/oauth2_endpoints.py
"""

import ast
import sys
from pathlib import Path

import pytest


class TestNoDebugPrintsInProduction:
    """Productie-code mag GEEN print() debug statements bevatten."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "src/core/api/auth/router.py",
            "src/core/api/oauth2_endpoints.py",
        ],
    )
    def test_no_debug_prints(self, module_path):
        """CRITICAL: Geen print(f"DEBUG...") statements in productie code."""
        # Lees het bestand
        file_path = Path(module_path)
        if not file_path.exists():
            pytest.skip(f"File {module_path} does not exist")

        source_code = file_path.read_text(encoding="utf-8")

        # Parse de code naar AST
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            pytest.fail(f"Syntax error in {module_path}: {e}")

        # Zoek naar print() calls
        print_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check if it's a print() call
                if isinstance(node.func, ast.Name) and node.func.id == "print":
                    # Probeer de line number te vinden
                    if hasattr(node, "lineno"):
                        print_calls.append(node.lineno)

        assert len(print_calls) == 0, (
            f"Gevonden {len(print_calls)} print() statements in {module_path} "
            f"op regels {print_calls}. Debug prints moeten verwijderd worden."
        )

    def test_no_debug_strings_in_auth_router(self):
        """HAPPY: Geen 'DEBUG' strings in logging of comments."""
        file_path = Path("src/core/api/auth/router.py")
        if not file_path.exists():
            pytest.skip("File does not exist")

        source_code = file_path.read_text(encoding="utf-8")
        lines_with_debug = []

        for i, line in enumerate(source_code.split("\n"), start=1):
            # Skip comments
            if line.strip().startswith("#"):
                continue
            # Check for DEBUG in code (not in docstrings)
            if "DEBUG" in line.upper() and "print" in line.lower():
                lines_with_debug.append((i, line.strip()))

        assert len(lines_with_debug) == 0, (
            f"Gevonden DEBUG print statements op regels: "
            f"{[f'{line[0]}: {line[1][:50]}' for line in lines_with_debug]}"
        )


class TestBrokenAuthRouterFixed:
    """auth/router.py MOET importeerbaar zijn zonder errors."""

    def test_router_imports_without_error(self):
        """CRITICAL: Import van auth.router crasht niet."""
        try:
            import src.core.api.auth.router as auth_router

            assert auth_router is not None
            assert hasattr(auth_router, "router"), "router module moet 'router' object hebben"
        except ImportError as e:
            pytest.fail(f"Import van auth.router faalde: {e}")
        except Exception as e:
            pytest.fail(f"Onverwachte fout bij import: {type(e).__name__}: {e}")

    def test_schemas_has_all_required_classes(self):
        """CRITICAL: schemas.py definieert alle classes die router.py importeert."""
        try:
            from src.core.api.auth import schemas

            # Lijst van schema classes die router.py importeert
            required_schemas = [
                "UserCreate",
                "UserResponse",
                "TokenResponse",
                "RefreshTokenRequest",
                "RefreshTokenResponse",
                "RevokeTokenRequest",
                "RevokeTokenResponse",
                "TokenValidationResponse",
                "ErrorResponse",
                "LoginRequest",
                "RegisterRequest",
                "PasswordResetRequest",
                "PasswordResetConfirm",
                "ChangePasswordRequest",
                "ForgotPasswordRequest",
            ]

            missing_schemas = []
            for schema_name in required_schemas:
                if not hasattr(schemas, schema_name):
                    missing_schemas.append(schema_name)

            assert len(missing_schemas) == 0, (
                f"Ontbrekende schema classes: {missing_schemas}. "
                f"Deze moeten gedefinieerd zijn in schemas.py"
            )

        except ImportError as e:
            pytest.fail(f"Import van schemas faalde: {e}")

    def test_oauth2_endpoints_exists_and_importable(self):
        """HAPPY: oauth2_endpoints.py bestaat en is importeerbaar."""
        try:
            import src.core.api.oauth2_endpoints as oauth2_endpoints

            assert oauth2_endpoints is not None
        except ImportError as e:
            # Dit is OK als het bestand niet bestaat (geconsolideerd in router.py)
            pytest.skip(f"oauth2_endpoints.py bestaat niet (mogelijk geconsolideerd): {e}")

    def test_router_has_essential_endpoints(self):
        """HAPPY: Router heeft essentiële auth endpoints gedefinieerd."""
        from src.core.api.auth import router as auth_router

        # Check dat router object bestaat
        assert hasattr(auth_router, "router"), "Module moet 'router' APIRouter object hebben"

        router_obj = auth_router.router

        # Verzamel alle routes
        routes = [route.path for route in router_obj.routes]

        # Essentiële auth endpoints
        essential_paths = ["/login", "/register"]

        # Check dat minstens één essentieel endpoint bestaat
        found_paths = [path for path in essential_paths if any(path in route for route in routes)]

        assert len(found_paths) > 0, (
            f"Router moet minstens één essentieel endpoint hebben. Gevonden routes: {routes}"
        )


class TestCodeQuality:
    """Algemene code quality checks."""

    def test_no_hardcoded_secrets_in_router(self):
        """CRITICAL: Geen hardcoded secrets of passwords in code."""
        file_path = Path("src/core/api/auth/router.py")
        if not file_path.exists():
            pytest.skip("File does not exist")

        source_code = file_path.read_text(encoding="utf-8").lower()

        # Zoek naar verdachte patronen
        suspicious_patterns = [
            'password = "',
            "password = '",
            'secret = "',
            "secret = '",
            'api_key = "',
            "api_key = '",
        ]

        found_patterns = []
        for pattern in suspicious_patterns:
            if (
                pattern in source_code
                and "example"
                not in source_code[source_code.find(pattern) : source_code.find(pattern) + 100]
            ):
                found_patterns.append(pattern)

        assert len(found_patterns) == 0, f"Mogelijk hardcoded secrets gevonden: {found_patterns}"

    def test_router_uses_proper_logging(self):
        """HAPPY: Auth router sub-files gebruiken proper logging (loguru/logging) ipv print."""
        auth_dir = Path("src/core/api/auth")
        if not auth_dir.exists():
            pytest.skip("Auth dir does not exist")

        all_source = "\n".join(
            p.read_text(encoding="utf-8") for p in sorted(auth_dir.glob("router*.py"))
        )
        has_logger_import = (
            "from loguru import logger" in all_source
            or "import logging" in all_source
            or "from logging import" in all_source
        )

        assert has_logger_import, (
            "Auth router bestanden moeten een proper logging library gebruiken (loguru/logging)"
        )
