"""Test for duplicate CVA routes.

Ref: CVA Audit Phase 2 - Task 2.1
"""

import ast
from pathlib import Path

import pytest


class TestNoDuplicateCVARoutes:
    """Only one file should define POST /api/v1/cva/chat."""

    def test_chat_endpoints_no_cva_chat_post_route(self):
        """chat_endpoints.py must not define a POST /api/v1/cva/chat route."""
        source_path = Path("src/core/api/chat_endpoints.py")
        if not source_path.exists():
            pytest.skip("chat_endpoints.py does not exist")

        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # Look for @router.post("/api/v1/cva/chat", ...) decorators
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "post":
                    # Check first argument (the path)
                    if node.args:
                        first_arg = node.args[0]
                        if isinstance(first_arg, ast.Constant) and "/cva/chat" in first_arg.value:
                            assert False, (
                                f"Duplicate POST /api/v1/cva/chat route found at line {node.lineno}. "
                                "Remove it - cva_endpoints.py is the canonical location."
                            )

    def test_cva_chat_has_chat_route(self):
        """cva_chat.py should define the canonical /chat route (included under /api/v1/cva prefix)."""
        # ADR-033: Route moved to v1/cva/chat_router.py
        source_path = Path("src/core/api/v1/cva/chat_router.py")
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # Look for @chat_router.post("/chat", ...) decorator
        found_chat_route = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "post":
                    if node.args:
                        first_arg = node.args[0]
                        if isinstance(first_arg, ast.Constant) and first_arg.value == "/chat":
                            found_chat_route = True
                            break

        assert found_chat_route, (
            "Canonical POST /chat route not found in chat_router.py. "
            "Router is included with prefix='/api/v1/cva', so /chat becomes /api/v1/cva/chat"
        )
