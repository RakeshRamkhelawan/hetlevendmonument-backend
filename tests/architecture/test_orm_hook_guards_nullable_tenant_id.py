"""DB-AUDIT-003 -- regression guard against undocumented nullable tenant_id models
(Sprint Dag 1 Groep 4, AUDIT-ARCH-2026-07-02).

The agentic domain's 6 models had a nullable tenant_id column with no exception
documentation anywhere -- a silent tenant-isolation gap (NULL rows are invisible to
both the ORM auto-filter in tenant_query_filter.py and any RLS policy comparing
tenant_id = <context>). This test scans every registered SQLAlchemy model for a
tenant_id column and fails if it is nullable=True without an explicit, documented
exception in _NULLABLE_TENANT_ID_EXCEPTIONS below.

TODO(SP-DATA-ARCH-1): discovered while building this guard (2026-07-02) -- 3 more
undocumented nullable tenant_id models outside the agentic domain, out of scope for
Groep 4:
- src/core/database/models/experiment.py::Experiment ("experiments")
- src/core/notifications/inbound/models.py::ContactOptOut ("contact_opt_outs")
- src/core/notifications/inbound/models.py::EmailBounce ("email_bounces")

register_all_models() (used for Alembic autogenerate too) does not import
src.core.notifications.inbound.models, so ContactOptOut/EmailBounce only appear on
Base.registry.mappers once something else imports that module -- this test imports it
explicitly below so the scan is deterministic regardless of test execution order (in
a fully-running app, every model module eventually gets imported anyway).
"""

# Ensures ContactOptOut/EmailBounce are registered even if this test runs in
# isolation -- see TODO(SP-DATA-ARCH-1) above.
import src.core.notifications.inbound.models  # noqa: F401
from src.core.database.database import Base
from src.core.database.model_registry import register_all_models

# Explicit, documented exceptions: a nullable tenant_id here is a deliberate design
# choice, not an oversight. Each entry MUST include a one-line justification.
_NULLABLE_TENANT_ID_EXCEPTIONS = {
    # System-wide audit trail -- ADR-019, excluded from tenant auto-filter in
    # tenant_query_filter.py (audit records must remain visible cross-tenant to
    # platform operators/compliance officers).
    "audit_logs": "system-wide audit trail (ADR-019), not tenant-scoped by design",
}

# TODO(SP-DATA-ARCH-1): known, not-yet-fixed violations (out of scope for Groep 4).
# Intentionally excluded from this allowlist -- see the dedicated RED tests below,
# per this project's rule that a deferred finding gets a failing test, not a silent
# allowlist entry.
_KNOWN_UNRESOLVED_VIOLATIONS = {"experiments", "contact_opt_outs", "email_bounces"}


def _scan_nullable_tenant_id_models() -> set[str]:
    register_all_models()
    violations = set()
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        tablename = getattr(cls, "__tablename__", None)
        if tablename is None or tablename in _NULLABLE_TENANT_ID_EXCEPTIONS:
            continue
        for column in mapper.columns:
            if column.name == "tenant_id" and column.nullable:
                violations.add(tablename)
    return violations


def test_agentic_domain_models_no_longer_have_nullable_tenant_id() -> None:
    """The 6 agentic-domain models fixed in Groep 4 must not regress."""
    agentic_tables = {
        "prompt_templates",
        "features",
        "tool_definitions",
        "prompt_metrics",
        "session_messages",
        "prompt_experiments",
    }
    violations = _scan_nullable_tenant_id_models()
    regressed = violations & agentic_tables
    assert not regressed, (
        f"Agentic-domain tenant_id NOT NULL regression: {regressed} -- "
        "DATA-001/DB-AUDIT-001 fix (Groep 4) was reverted."
    )


def test_experiments_tenant_id_is_documented_or_fixed() -> None:
    """TODO(SP-DATA-ARCH-1): "experiments" (src/core/database/models/experiment.py)
    has a nullable tenant_id with no documented justification. Not fixed today (out
    of scope for Groep 4). Intentionally RED until it is either set nullable=False or
    added to _NULLABLE_TENANT_ID_EXCEPTIONS with a real justification."""
    violations = _scan_nullable_tenant_id_models()
    assert "experiments" not in violations, (
        "SP-DATA-ARCH-1 backlog not yet resolved -- 'experiments' table still has "
        "nullable tenant_id with no documented exception."
    )


def test_notifications_inbound_tenant_id_is_documented_or_fixed() -> None:
    """TODO(SP-DATA-ARCH-1): ContactOptOut/EmailBounce
    (src/core/notifications/inbound/models.py) have nullable tenant_id with no
    documented justification. Not fixed today (out of scope for Groep 4).
    Intentionally RED until fixed or documented."""
    violations = _scan_nullable_tenant_id_models()
    still_broken = violations & {"contact_opt_outs", "email_bounces"}
    assert not still_broken, (
        f"SP-DATA-ARCH-1 backlog not yet resolved -- {still_broken} still have "
        "nullable tenant_id with no documented exception."
    )


def test_no_new_undocumented_nullable_tenant_id_models() -> None:
    """Regression guard: any model beyond the currently-known backlog items is a
    genuinely NEW, previously-undiscovered violation."""
    violations = _scan_nullable_tenant_id_models()
    new_undocumented = violations - _KNOWN_UNRESOLVED_VIOLATIONS
    assert not new_undocumented, (
        f"New undocumented nullable-tenant_id model(s): {new_undocumented}. "
        "Either set nullable=False, or add an entry to _NULLABLE_TENANT_ID_EXCEPTIONS "
        "with a one-line justification."
    )
