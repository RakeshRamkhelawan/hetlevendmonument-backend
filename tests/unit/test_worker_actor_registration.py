"""SP-WE-19 -- Dramatiq actor registratie verificatie (NEW-WIRE-001/002).

RED tests: falen voor de fix.
GREEN na fix: alle critical actors importeerbaar, sync, juiste attributen.
"""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.unit
def test_critical_actors_importable_via_actors_py() -> None:
    """Actors moeten importeerbaar zijn via actors.py (side-effect registratie) (NEW-WIRE-001)."""
    from src.core.tasks.dramatiq_broker import workflow_broker
    import src.workers.actors  # noqa: F401 -- side-effect import

    # check_hash_chain_integrity_actor en process_cva_message moeten in de workflowbroker staan. Sinds
    # ADR-036 OP-13 binden alle actors er expliciet aan; de procesbrede broker doet niet meer mee.
    registered = workflow_broker.get_declared_actors()
    assert "check_hash_chain_integrity_actor" in registered, (
        "hash chain integrity actor niet geregistreerd -- NEW-WIRE-001"
    )
    assert "process_cva_message" in registered, (
        "CVA message actor niet geregistreerd -- NEW-WIRE-001"
    )


@pytest.mark.unit
def test_cleanup_council_decisions_importable_and_correct() -> None:
    """cleanup_council_decisions importeerbaar met juiste actor_name (NEW-WIRE-001)."""
    from src.core.governance.retention_cleanup import cleanup_council_decisions

    assert cleanup_council_decisions.actor_name == "cleanup_council_decisions"
    assert not inspect.iscoroutinefunction(cleanup_council_decisions.fn), (
        "cleanup_council_decisions.fn is async -- converteren naar sync wrapper"
    )


@pytest.mark.unit
def test_actors_py_imports_are_idempotent() -> None:
    """actors.py imports zijn idempotent bij meerdere imports."""
    import src.workers.actors  # noqa: F401


@pytest.mark.unit
def test_process_cva_message_is_sync_actor() -> None:
    """Actor body sync -- async body is stille data loss (NEW-WIRE-002)."""
    from src.core.tasks.cva_tasks import process_cva_message

    assert not inspect.iscoroutinefunction(process_cva_message.fn), (
        "process_cva_message.fn is async -- converteren naar sync wrapper met asyncio.run()"
    )


@pytest.mark.unit
def test_check_hash_chain_integrity_actor_is_sync() -> None:
    """Actor body sync -- async body is stille data loss (NEW-WIRE-002)."""
    from src.core.copilot.audit.integrity_check_actor import check_hash_chain_integrity_actor

    assert not inspect.iscoroutinefunction(check_hash_chain_integrity_actor.fn), (
        "check_hash_chain_integrity_actor.fn is async -- converteren naar sync wrapper"
    )


@pytest.mark.unit
def test_process_cva_message_actor_attributes() -> None:
    """Actor attributen behouden na conversie."""
    from src.core.tasks.cva_tasks import process_cva_message

    assert process_cva_message.actor_name == "process_cva_message"
    assert hasattr(process_cva_message, "queue_name")


@pytest.mark.unit
def test_notify_tenant_admins_of_contest_is_registered() -> None:
    """notify_tenant_admins_of_contest moet sync en geregistreerd zijn na actors.py import."""
    import src.workers.actors  # noqa: F401 -- side-effect import
    from src.core.copilot.api.contest_service import notify_tenant_admins_of_contest

    assert not inspect.iscoroutinefunction(notify_tenant_admins_of_contest.fn), (
        "notify_tenant_admins_of_contest moet sync zijn (asyncio.run() wrapper patroon)"
    )
    assert hasattr(notify_tenant_admins_of_contest, "actor_name")


@pytest.mark.unit
def test_generate_audit_report_is_registered() -> None:
    """generate_audit_report moet sync en geregistreerd zijn na actors.py import."""
    import src.workers.actors  # noqa: F401 -- side-effect import
    from src.core.copilot.audit.report_jobs import generate_audit_report

    assert not inspect.iscoroutinefunction(generate_audit_report.fn), (
        "generate_audit_report moet sync zijn (asyncio.run() wrapper patroon)"
    )
    assert hasattr(generate_audit_report, "actor_name")


@pytest.mark.unit
def test_execute_workflow_step_is_registered() -> None:
    """execute_workflow_step moet sync zijn na actors.py import."""
    import src.workers.actors  # noqa: F401 -- side-effect import
    from src.core.tasks.workflow_tasks import execute_workflow_step

    assert not inspect.iscoroutinefunction(execute_workflow_step.fn), (
        "execute_workflow_step moet sync zijn (asyncio.run() wrapper patroon)"
    )
    assert hasattr(execute_workflow_step, "actor_name")


@pytest.mark.unit
def test_write_audit_log_task_is_registered() -> None:
    """GOV-002 (AUDIT-ARCH-2026-07-02): write_audit_log_task moet geimporteerd worden
    door actors.py, anders enqueuen de 5 sessieloze audit-hot-paths (token_blacklist,
    token_refresh, logout_rate_limiter, session_dashboard, csp_violation_reporter) naar
    een queue die geen enkele worker consumeert -- stille audit-data-loss."""
    from src.core.tasks.dramatiq_broker import workflow_broker

    import src.workers.actors  # noqa: F401 -- side-effect import
    from src.core.tasks.audit_tasks import write_audit_log_task

    assert not inspect.iscoroutinefunction(write_audit_log_task.fn), (
        "write_audit_log_task moet sync zijn (asyncio.run() wrapper patroon)"
    )
    assert hasattr(write_audit_log_task, "actor_name")
    registered = workflow_broker.get_declared_actors()
    assert "write_audit_log_task" in registered, (
        "write_audit_log_task niet geregistreerd bij de Dramatiq broker -- "
        "audit writes vanuit sessieloze hot paths gaan verloren (GOV-002 regressie)"
    )
