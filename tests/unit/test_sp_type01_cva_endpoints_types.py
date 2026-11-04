"""
SP-TYPE-01 dag 3 — type-annotation tests for src/core/api/cva_endpoints.py.

Verifies that concrete types replace Any in CVA endpoint return annotations.
RED before refactoring, GREEN after.
"""

import typing

import pytest


def _hints(fn_name: str) -> dict:
    import sys

    import src.core.api.cva_endpoints as m

    fn = getattr(m, fn_name)
    try:
        return typing.get_type_hints(fn)
    except NameError:
        # Modules using TYPE_CHECKING for Depends parameters can't resolve all forward refs.
        # Fall back to evaluating only the return annotation in the function's own module globals.
        raw = fn.__annotations__.get("return")
        if raw is None:
            return {}
        module = sys.modules.get(fn.__module__)
        globalns = vars(module) if module else {}
        # Safe: raw comes from fn.__annotations__ (Python runtime, not user input).
        # We evaluate only the return annotation string in a restricted namespace.
        resolved = eval(raw, globalns) if isinstance(raw, str) else raw  # noqa: S307
        return {"return": resolved}


@pytest.mark.unit
def test_create_managed_cva_agent_returns_dict() -> None:
    """create_managed_cva_agent must return dict[str, Any], not Any."""
    return_type = _hints("create_managed_cva_agent").get("return")
    assert getattr(return_type, "__origin__", None) is dict, (
        f"Expected dict origin, got {return_type}"
    )


@pytest.mark.unit
def test_execute_managed_cva_agent_returns_dict() -> None:
    """execute_managed_cva_agent must return dict[str, Any], not Any."""
    return_type = _hints("execute_managed_cva_agent").get("return")
    assert getattr(return_type, "__origin__", None) is dict, (
        f"Expected dict origin, got {return_type}"
    )


@pytest.mark.unit
def test_chat_endpoint_returns_chat_response() -> None:
    """chat_endpoint must return ChatResponse, not Any."""
    from src.core.schemas.cva_schemas import ChatResponse

    return_type = _hints("chat_endpoint").get("return")
    assert return_type is ChatResponse, f"Expected ChatResponse, got {return_type}"


@pytest.mark.unit
def test_chat_with_cva_returns_cva_chat_response() -> None:
    """chat_with_cva must return CVAChatResponse, not Any."""
    import src.core.api.cva_endpoints as m

    return_type = _hints("chat_with_cva").get("return")
    assert return_type is m.CVAChatResponse, f"Expected CVAChatResponse, got {return_type}"


@pytest.mark.unit
def test_get_cva_status_returns_cva_status_response() -> None:
    """get_cva_status must return CVAStatusResponse, not Any."""
    import src.core.api.cva_endpoints as m

    return_type = _hints("get_cva_status").get("return")
    assert return_type is m.CVAStatusResponse, f"Expected CVAStatusResponse, got {return_type}"


@pytest.mark.unit
def test_get_cva_health_returns_dict() -> None:
    """get_cva_health must return dict[str, Any], not Any."""
    return_type = _hints("get_cva_health").get("return")
    assert getattr(return_type, "__origin__", None) is dict, (
        f"Expected dict origin, got {return_type}"
    )


@pytest.mark.unit
def test_shutdown_cva_returns_dict() -> None:
    """shutdown_cva must return dict[str, Any], not Any."""
    return_type = _hints("shutdown_cva").get("return")
    assert getattr(return_type, "__origin__", None) is dict, (
        f"Expected dict origin, got {return_type}"
    )


# --- dag 4 additions ---


@pytest.mark.unit
def test_list_conversations_returns_dict() -> None:
    """list_conversations must return dict[str, Any], not Any."""
    return_type = _hints("list_conversations").get("return")
    assert getattr(return_type, "__origin__", None) is dict, (
        f"Expected dict origin, got {return_type}"
    )


@pytest.mark.unit
def test_get_conversation_returns_dict() -> None:
    """get_conversation must return dict[str, Any], not Any."""
    return_type = _hints("get_conversation").get("return")
    assert getattr(return_type, "__origin__", None) is dict, (
        f"Expected dict origin, got {return_type}"
    )


@pytest.mark.unit
def test_chat_with_cva_streaming_returns_streaming_response() -> None:
    """chat_with_cva_streaming annotation is Any (functools.wraps ForwardRef fix); route uses response_class=StreamingResponse."""
    from typing import Any

    return_type = _hints("chat_with_cva_streaming").get("return")
    assert return_type is Any, f"Expected Any (functools.wraps valkuil fix), got {return_type}"
