"""Test for CVA schema consistency.

Ref: CVA Audit Phase 2 - Task 2.2
"""

import ast
from pathlib import Path

import pytest


class TestNoDuplicateSchemas:
    """cva_chat.py must not define its own Pydantic models for chat."""

    def test_no_inline_chat_request_response_in_endpoints(self):
        """ChatRequest/ChatResponse should be imported from cva_schemas, not inline."""
        # SP-API migration: check v1/cva/chat_router.py
        source_path = Path("src/core/api/v1/cva/chat_router.py")
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        inline_models = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = ""
                    if isinstance(base, ast.Name):
                        base_name = base.id
                    elif isinstance(base, ast.Attribute):
                        base_name = base.attr
                    if base_name == "BaseModel":
                        # Check if it's a chat-related model
                        if "Chat" in node.name and node.name not in [
                            "CVAStatusResponse",
                            "CVACreateAgentRequest",
                            "CVAExecuteAgentRequest",
                            "CVAChatRequest",
                            "CVAChatResponse",
                        ]:
                            inline_models.append(node.name)

        # Allow CVAChatRequest/CVAChatResponse for legacy endpoint
        # But ensure they are distinct from ChatRequest/ChatResponse
        assert "ChatRequest" not in inline_models, (
            f"Inline ChatRequest found: {inline_models}. "
            "Use ChatRequest from src.core.schemas.cva_schemas instead."
        )
        assert "ChatResponse" not in inline_models, (
            f"Inline ChatResponse found: {inline_models}. "
            "Use ChatResponse from src.core.schemas.cva_schemas instead."
        )

    def test_chat_request_imported_from_schemas(self):
        """Verify ChatRequest is imported from cva_schemas."""
        # SP-API migration: check v1/cva/chat_router.py
        source_path = Path("src/core/api/v1/cva/chat_router.py")
        source = source_path.read_text(encoding="utf-8")

        # Should import ChatRequest from cva_schemas
        assert "from src.core.schemas.cva_schemas import" in source, (
            "ChatRequest/ChatResponse should be imported from cva_schemas"
        )
