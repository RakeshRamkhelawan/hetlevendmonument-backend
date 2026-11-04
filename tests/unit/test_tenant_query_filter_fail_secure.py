"""
Tests: ORM tenant filter fail-secure exception handling.

RED PHASE:
  These tests FAIL with current code because both except blocks are fail-open
  (they log and silently return, letting unfiltered queries pass through).

GREEN PHASE (after fix):
  Both except blocks inject WHERE 1=0, blocking the query instead of leaking data.

Two vulnerable blocks in auto_filter_by_tenant():
  1. except (AttributeError, InvalidRequestError) -- inner block
  2. except Exception                              -- outer block

Project conventions:
  - ASCII only in source
  - 100-char line length
  - pytest markers: unit + security
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import InvalidRequestError

import src.core.database.tenant_query_filter as _tqf_module
from src.core.database.tenant_query_filter import TenantFilterBypass


# ============================================================================
# FIXTURE: capture the raw hook function without double-registering
# ============================================================================


@pytest.fixture(scope="module")
def hook_fn():
    """
    Extract auto_filter_by_tenant directly by intercepting event.listens_for.

    Replaces the module-level `event` reference in tenant_query_filter.py with
    a mock whose listens_for captures the decorated function, then restores it.
    This avoids registering the listener a second time in SQLAlchemy's event
    system (which would cause double filtering in unrelated tests).
    """
    captured = {}

    mock_event = MagicMock()

    def fake_listens_for(target, identifier, **kw):
        def decorator(fn):
            captured["hook"] = fn
            # Do NOT call sa_event.listen() -- we are capturing, not re-registering.
            return fn

        return decorator

    mock_event.listens_for.side_effect = fake_listens_for

    original_event = _tqf_module.event
    _tqf_module.event = mock_event
    try:
        _tqf_module.init_tenant_auto_filtering()
    finally:
        _tqf_module.event = original_event

    assert "hook" in captured, "Failed to capture auto_filter_by_tenant from init_tenant_auto_filtering()"
    return captured["hook"]


# ============================================================================
# HELPER
# ============================================================================


def _make_select_state_with_bad_entity(exception_type):
    """
    Build a mock orm_execute_state for a SELECT where entity inspection fails.

    entity.get() raises `exception_type`, simulating an inspection error that
    lands in one of the two fail-open except blocks.

    Returns (state, stmt) so callers can assert on stmt.where.
    """
    bad_entity = MagicMock()
    bad_entity.get.side_effect = exception_type("simulated entity inspection error")

    stmt = MagicMock()
    stmt.is_select = True
    stmt.is_update = False
    stmt.is_delete = False
    stmt.column_descriptions = [bad_entity]
    stmt.where = MagicMock(return_value=stmt)

    state = MagicMock()
    state.statement = stmt

    return state, stmt


# ============================================================================
# TEST: inner except (AttributeError, InvalidRequestError) -- must fail-secure
# ============================================================================


@pytest.mark.unit
@pytest.mark.security
class TestFailSecureInnerExcept:
    """
    Inner except block catches AttributeError and InvalidRequestError.

    CURRENT (fail-open):  logs warning, silently returns -> unfiltered query leaks data.
    REQUIRED (fail-secure): inject WHERE 1=0 -> query returns empty set.
    """

    def test_attribute_error_in_entity_inspection_blocks_query(self, hook_fn):
        """
        AttributeError during column_descriptions inspection must block query.

        RED: stmt.where is NOT called (fail-open -> data leak possible).
        GREEN: stmt.where IS called once with literal(False) (fail-secure).
        """
        state, stmt = _make_select_state_with_bad_entity(AttributeError)

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "src.core.middleware.tenant_context.get_tenant_id",
                lambda: 42,
            )
            hook_fn(state)

        # Fail-secure: WHERE 1=0 must have been injected to block the query.
        stmt.where.assert_called_once()

    def test_invalid_request_error_in_entity_inspection_blocks_query(self, hook_fn):
        """
        InvalidRequestError during column_descriptions inspection must block query.

        RED: stmt.where is NOT called (fail-open -> data leak possible).
        GREEN: stmt.where IS called once with literal(False) (fail-secure).
        """
        state, stmt = _make_select_state_with_bad_entity(InvalidRequestError)

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "src.core.middleware.tenant_context.get_tenant_id",
                lambda: 42,
            )
            hook_fn(state)

        # Fail-secure: WHERE 1=0 must have been injected to block the query.
        stmt.where.assert_called_once()


# ============================================================================
# TEST: outer except Exception -- must fail-secure
# ============================================================================


@pytest.mark.unit
@pytest.mark.security
class TestFailSecureOuterExcept:
    """
    Outer except block catches all exceptions not caught by the inner block.

    CURRENT (fail-open):  logs error, silently returns -> unfiltered query leaks data.
    REQUIRED (fail-secure): inject WHERE 1=0 -> query returns empty set.
    """

    def test_generic_exception_in_entity_inspection_blocks_query(self, hook_fn):
        """
        RuntimeError (not AttributeError/InvalidRequestError) must block query.

        RuntimeError is caught only by the outer `except Exception` block, not the
        inner `except (AttributeError, InvalidRequestError)` block.

        RED: stmt.where is NOT called (fail-open -> data leak possible).
        GREEN: stmt.where IS called once with literal(False) (fail-secure).
        """
        # RuntimeError is NOT in (AttributeError, InvalidRequestError),
        # so it falls through to outer except Exception.
        state, stmt = _make_select_state_with_bad_entity(RuntimeError)

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "src.core.middleware.tenant_context.get_tenant_id",
                lambda: 42,
            )
            hook_fn(state)

        # Fail-secure: WHERE 1=0 must have been injected to block the query.
        stmt.where.assert_called_once()

    def test_type_error_in_entity_inspection_blocks_query(self, hook_fn):
        """
        TypeError (another non-AttributeError exception) must block query.

        Additional coverage for the outer except Exception block.
        """
        state, stmt = _make_select_state_with_bad_entity(TypeError)

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "src.core.middleware.tenant_context.get_tenant_id",
                lambda: 42,
            )
            hook_fn(state)

        stmt.where.assert_called_once()


# ============================================================================
# TEST: no regression -- bypass and no-tenant paths must not be affected
# ============================================================================


@pytest.mark.unit
@pytest.mark.security
class TestNoRegressions:
    """
    Ensure fail-secure changes do not break existing safe paths:
      - Bypass (TenantFilterBypass) still skips filtering.
      - No tenant context still injects WHERE 1=0 (existing behaviour).
    """

    def test_bypass_active_hook_returns_early_without_touching_statement(self, hook_fn):
        """
        With TenantFilterBypass(), the hook must return before reaching the
        entity inspection code, so stmt.where is never called.
        """
        state, stmt = _make_select_state_with_bad_entity(AttributeError)

        from src.core.database.tenant_query_filter import _bypass_tenant_filter

        token = _bypass_tenant_filter.set(True)
        try:
            with pytest.MonkeyPatch().context() as mp:
                mp.setattr(
                    "src.core.middleware.tenant_context.get_tenant_id",
                    lambda: 42,
                )
                hook_fn(state)
        finally:
            _bypass_tenant_filter.reset(token)

        # Bypass: hook returns early, stmt.where never called.
        stmt.where.assert_not_called()

    def test_no_tenant_context_still_injects_where_false(self, hook_fn):
        """
        When get_tenant_id() returns None, existing fail-secure logic injects
        WHERE 1=0. This path must remain unaffected by the new fix.
        """
        # Normal entity (would be filtered if tenant_id were set).
        stmt = MagicMock()
        stmt.is_select = True
        stmt.is_update = False
        stmt.is_delete = False
        stmt.where = MagicMock(return_value=stmt)

        state = MagicMock()
        state.statement = stmt

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "src.core.middleware.tenant_context.get_tenant_id",
                lambda: None,
            )
            hook_fn(state)

        # Existing fail-secure: WHERE 1=0 applied when no tenant context.
        stmt.where.assert_called_once()
