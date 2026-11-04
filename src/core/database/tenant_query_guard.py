"""Compatibility bridge for tenant query guard registration.

Historically, database initialization and tests imported several helpers from
``tenant_query_guard``. The current implementation lives mostly in
``tenant_query_filter`` as ``init_tenant_auto_filtering``.

This module preserves the old import path and compatibility surface while the
new filter engine remains the single implementation of runtime behavior.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any
from collections.abc import Iterable

from sqlalchemy.engine import Engine

from .tenant_query_filter import (
    TenantFilterBypass,
    _bypass_tenant_filter,
    init_tenant_auto_filtering,
    remove_tenant_auto_filtering,
)

_GUARD_REGISTERED = False


class TenantFilterMissingError(RuntimeError):
    """Raised when a tenant-scoped query is missing a tenant filter."""

    def __init__(self, table_name: str, statement_type: str) -> None:
        self.table_name = table_name
        self.statement_type = statement_type
        super().__init__(
            f"SECURITY VIOLATION: {statement_type} query on {table_name} is missing tenant filter"
        )


def _is_bypass_active() -> bool:
    """Return whether tenant filter bypass is active in the current context."""

    return bool(_bypass_tenant_filter.get())


def _extract_table_names_from_query(statement: Any) -> set[str]:  # TODO(TYPE): replace Any with concrete type
    """Extract table names from simple SQLAlchemy statements or test doubles."""

    table_names: set[str] = set()

    for from_clause in getattr(statement, "froms", ()) or ():
        table_name = getattr(from_clause, "name", None)
        if table_name:
            table_names.add(str(table_name))

    table = getattr(statement, "table", None)
    table_name = getattr(table, "name", None)
    if table_name:
        table_names.add(str(table_name))

    return table_names


def _has_tenant_filter(statement: Any) -> bool:  # TODO(TYPE): replace Any with concrete type
    """Detect whether a statement contains a tenant_id predicate."""

    where_criteria: Iterable[Any] = getattr(statement, "_where_criteria", ()) or ()  # TODO(TYPE): replace Any with concrete type
    for criterion in where_criteria:
        text = str(criterion)
        if re.search(r'"?tenant_id"?\s*(=|IN\s*\(|IS\s+NULL)', text, re.IGNORECASE):
            return True
    return False


@lru_cache(maxsize=1)
def _get_tenant_scoped_tables() -> set[str]:
    """Return the known tenant-scoped table names from the ORM registry."""

    try:
        from src.core.database.database import Base

        tables = {
            mapper.persist_selectable.name
            for mapper in Base.registry.mappers
            if hasattr(mapper.class_, "tenant_id") and hasattr(mapper.persist_selectable, "name")
        }
        return {str(name) for name in tables}
    except Exception:
        return set()


def get_guard_status() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Return a simple status payload for diagnostics and tests."""

    tables = _get_tenant_scoped_tables()
    return {
        "bypass_active": _is_bypass_active(),
        "tenant_scoped_tables_count": len(tables),
        "tenant_scoped_tables": sorted(tables),
    }


def register_query_guard(_engine: Engine | None = None) -> None:
    """Register global tenant auto-filtering hooks once.

    The SQLAlchemy event registration in ``init_tenant_auto_filtering`` is
    process-global and does not require direct engine wiring.

    ``_engine`` wordt niet gebruikt en mag daarom None zijn -- de parameter staat er voor de
    aanroepers die hem historisch meegeven.
    """

    global _GUARD_REGISTERED
    if _GUARD_REGISTERED:
        return

    init_tenant_auto_filtering()
    _GUARD_REGISTERED = True


def remove_query_guard() -> None:
    """Zet de globale tenantfilter-registratie helemaal terug.

    Doet TWEE dingen, en dat is de kern: de listener weghalen EN ``_GUARD_REGISTERED`` terugzetten.

    Die vlag was een eenrichtingslatch die nergens werd gereset. Wie alleen
    ``remove_tenant_auto_filtering()`` aanroept, zorgt dat ``register_query_guard()`` daarna
    vroegtijdig terugkeert en het tenantfilter PERMANENT afwezig is. Een fail-secure filter wordt
    dan geen filter, en tenant-isolatietests blijven groen terwijl ze niets handhaven -- dat is
    de gevaarlijke richting, en precies waarom deze functie bestaat in plaats van dat elke
    aanroeper de twee stappen zelf combineert.

    Bedoeld voor testopstellingen (zie ``_do_global_reset`` in ``tests/conftest.py``). In de
    applicatie blijft de registratie staan voor de hele levensduur van het proces.
    """

    global _GUARD_REGISTERED
    remove_tenant_auto_filtering()
    _GUARD_REGISTERED = False


__all__ = [
    "TenantFilterBypass",
    "TenantFilterMissingError",
    "_extract_table_names_from_query",
    "_get_tenant_scoped_tables",
    "_has_tenant_filter",
    "_is_bypass_active",
    "get_guard_status",
    "register_query_guard",
    "remove_query_guard",
]
