"""
SP-TYPE-01 dag 2 — type-annotation tests for src/core/api/main.py.

These tests verify that concrete types replace Any in the API layer.
They are RED before refactoring and GREEN after.
"""

import typing

import pytest


@pytest.mark.unit
def test_http_exception_handler_request_is_starlette_request() -> None:
    """request parameter in http_exception_handler must be starlette.Request, not Any."""
    from starlette.requests import Request

    from src.core.api.main import http_exception_handler

    hints = typing.get_type_hints(http_exception_handler)
    assert hints.get("request") is Request, (
        f"http_exception_handler.request should be starlette.Request, got {hints.get('request')}"
    )


@pytest.mark.unit
def test_general_exception_handler_request_is_starlette_request() -> None:
    """request parameter in general_exception_handler must be starlette.Request, not Any."""
    from starlette.requests import Request

    from src.core.api.main import general_exception_handler

    hints = typing.get_type_hints(general_exception_handler)
    assert hints.get("request") is Request, (
        f"general_exception_handler.request should be starlette.Request, got {hints.get('request')}"
    )


@pytest.mark.unit
def test_lifespan_return_type_is_iterator_none() -> None:
    """lifespan must return AsyncIterator[None], not AsyncIterator[Any]."""
    import collections.abc

    from src.core.api.main import lifespan

    hints = typing.get_type_hints(lifespan)
    return_hint = hints.get("return")
    # AsyncIterator[None] origin is collections.abc.AsyncIterator
    origin = getattr(return_hint, "__origin__", None)
    args = getattr(return_hint, "__args__", ())
    assert origin is collections.abc.AsyncIterator, (
        f"lifespan return origin should be AsyncIterator, got {origin}"
    )
    # typing.get_type_hints evaluates 'None' annotation as None singleton, not type(None)
    assert args == (None,) or args == (type(None),), (
        f"lifespan return args should be (None,) or (NoneType,), got {args}"
    )
