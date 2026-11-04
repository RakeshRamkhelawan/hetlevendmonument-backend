"""Architecture tests: tenant-context propagatie in Dramatiq workers (SP-DLP-001).

Bevindingen gemeten 2026-06-25 -- alle tests zijn INTENTIONEEL ROOD totdat de
backlog-items gefixed zijn.

TI-001: cva_tasks.py roept set_tenant_id() niet aan -- tenant_id komt uit request
        body in plaats van via de ContextVar-middleware te worden gezet.
TI-002: report_jobs.py gebruikt set_config() (PostgreSQL session-level) in plaats
        van set_tenant_id() (Python ContextVar) -- SQLAlchemy ORM tenant filter
        (ADR-004 do_orm_execute hook) wordt niet geactiveerd.
TI-003: workflow_tasks.py roept set_tenant_id() niet aan -- AutonomousAgent heeft
        geen tenant-context bij uitvoering in de worker.
TI-004: workflow/worker.py gebruikt hardcoded tenant_id=1 in de engine factory --
        elke workflow-taak draait als system-tenant in plaats van de echte tenant.
TI-005: RegionalLearningStore._key() in multi_region.py bevat geen tenant_id in
        de Redis-sleutel -- keys van verschillende tenants overlappen elkaar.

TODO(SP-DLP-001): fix TI-001 -- voeg set_tenant_id(tenant_id) toe aan het begin
    van _process_cva_message_async() in src/core/tasks/cva_tasks.py.
TODO(SP-DLP-001): fix TI-002 -- vervang set_config() door set_tenant_id() in
    _generate_audit_report_async() in src/core/copilot/audit/report_jobs.py.
TODO(SP-DLP-001): fix TI-003 -- voeg set_tenant_id(task_data.tenant_id) toe aan
    execute_workflow_step() in src/core/tasks/workflow_tasks.py.
TODO(SP-DLP-001): fix TI-004 -- lees tenant_id uit message metadata of job-payload
    en zet via set_tenant_id() in create_workflow_engine() in src/core/workflow/worker.py.
TODO(SP-DLP-001): fix TI-005 -- voeg tenant_id toe aan de _key() methode in
    RegionalLearningStore in src/core/learning/multi_region.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# TI-001: cva_tasks.py
# ---------------------------------------------------------------------------


def test_ti001_cva_tasks_calls_set_tenant_id() -> None:
    """TI-001: cva_tasks.py MOET set_tenant_id() aanroepen voor ORM tenant filter.

    TODO(SP-DLP-001): voeg set_tenant_id(tenant_id) toe aan het begin van
    _process_cva_message_async() zodat de ADR-004 do_orm_execute hook de juiste
    WHERE-clause injecteert. Zonder deze aanroep draait de actor zonder
    tenant-context en lekt data tussen tenants.
    """
    src = (_REPO_ROOT / "src/core/tasks/cva_tasks.py").read_text(encoding="utf-8")
    assert "set_tenant_id" in src, (
        "TI-001 (SP-DLP-001): cva_tasks.py roept set_tenant_id() niet aan. "
        "Dramatiq workers draaien buiten de FastAPI middleware-keten; de ContextVar "
        "moet handmatig gezet worden. Voeg set_tenant_id(tenant_id) toe aan "
        "_process_cva_message_async() voor de eerste DB-aanroep."
    )


# ---------------------------------------------------------------------------
# TI-003: workflow_tasks.py
# ---------------------------------------------------------------------------


def test_ti003_workflow_tasks_calls_set_tenant_id() -> None:
    """TI-003: workflow_tasks.py MOET set_tenant_id() aanroepen voor ORM tenant filter.

    TODO(SP-DLP-001): voeg set_tenant_id(task_data.tenant_id) toe aan
    execute_workflow_step() zodat AutonomousAgent de correcte tenant-context
    heeft. Zonder deze aanroep draait de actor zonder tenant-context en kan
    data van andere tenants verwerkt worden.
    """
    src = (_REPO_ROOT / "src/core/tasks/workflow_tasks.py").read_text(encoding="utf-8")
    assert "set_tenant_id" in src, (
        "TI-003 (SP-DLP-001): workflow_tasks.py roept set_tenant_id() niet aan. "
        "execute_workflow_step() maakt een AutonomousAgent aan maar zet geen "
        "tenant-context via de ContextVar. Voeg set_tenant_id(task_data.tenant_id) "
        "toe voor asyncio.run()."
    )


# ---------------------------------------------------------------------------
# TI-004: workflow/worker.py
# ---------------------------------------------------------------------------


def test_ti004_workflow_engine_no_hardcoded_tenant_id_1() -> None:
    """TI-004: workers/workflow_worker.py mag tenant_id=1 niet hardcoded gebruiken.

    Deze test wees tot 2026-08-27 naar `src/core/workflow/worker.py`, bevestigd dode
    code (ADR-036 OP-158 D2b) en verwijderd. `src/workers/workflow_worker.py` is de
    ECHTE, gedeployde module -- gemeten (`grep -n "tenant_id=1" src/workers/
    workflow_worker.py`, geen treffers): `execute_workflow_task` leest `tenant_id` uit
    het `WorkflowExecution`-record (`select(WorkflowExecution.tenant_id)...`) en valt
    alleen op `_SYSTEM_TENANT_ID` terug als die kolom None is -- TI-004 is voor de
    LEVENDE module dus al opgelost, alleen niet eerder tegen het juiste bestand getoetst.
    """
    src = (_REPO_ROOT / "src/workers/workflow_worker.py").read_text(encoding="utf-8")
    assert "tenant_id=1" not in src, (
        "TI-004 (SP-DLP-001): workflow_worker.py bevat hardcoded tenant_id=1 in "
        "create_workflow_engine(). Elke workflow-taak draait als system-tenant. "
        "Lees tenant_id uit de job-payload en propageer via set_tenant_id()."
    )


# ---------------------------------------------------------------------------
# TI-005: learning/multi_region.py -- RegionalLearningStore._key()
# ---------------------------------------------------------------------------


def _get_key_method_body(source: str) -> str | None:
    """Geef de body van RegionalLearningStore._key() terug als string, of None."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "RegionalLearningStore"):
            continue
        for item in node.body:
            if not (isinstance(item, ast.FunctionDef) and item.name == "_key"):
                continue
            # Reconstruct the line range of the function body
            start = item.body[0].lineno - 1
            end = item.end_lineno  # type: ignore[attr-defined]
            lines = source.splitlines()[start:end]
            return "\n".join(lines)
    return None


def test_ti005_regional_learning_store_key_includes_tenant_id() -> None:
    """TI-005: RegionalLearningStore._key() MOET tenant_id opnemen in de Redis-sleutel.

    TODO(SP-DLP-001): voeg tenant_id toe aan de sleutel in _key() zodat Redis-keys
    van verschillende tenants niet overlappen. Huidige sleutel:
        'learning:{region.code}:{suffix}'
    Vereiste sleutel (minimaal):
        'learning:{tenant_id}:{region.code}:{suffix}'
    of equivalent via self.tenant_id.

    Zonder tenant_id in de sleutel kan tenant A de leerdata van tenant B lezen
    of overschrijven via RegionalLearningStore.
    """
    src = (_REPO_ROOT / "src/core/learning/multi_region.py").read_text(encoding="utf-8")
    body = _get_key_method_body(src)

    assert body is not None, (
        "TI-005 (SP-DLP-001): RegionalLearningStore._key() niet gevonden in "
        "src/core/learning/multi_region.py -- controleer of de klasse nog bestaat."
    )

    has_tenant_in_key = "tenant_id" in body or "self.tenant_id" in body
    assert has_tenant_in_key, (
        "TI-005 (SP-DLP-001): RegionalLearningStore._key() bevat geen 'tenant_id' "
        "in de methode-body. Redis-sleutels zijn niet tenant-gescheiden: "
        "tenant A kan leerdata van tenant B lezen of overschrijven. "
        "Voeg tenant_id toe: 'learning:{tenant_id}:{region.code}:{suffix}'."
    )


# ---------------------------------------------------------------------------
# TI-002: copilot/audit/report_jobs.py
# ---------------------------------------------------------------------------


def test_ti002_report_jobs_uses_set_tenant_id_not_set_config() -> None:
    """TI-002: report_jobs.py MOET set_tenant_id() gebruiken, niet set_config().

    TODO(SP-DLP-001): vervang de set_config('app.current_tenant', ...) aanroep
    in _generate_audit_report_async() door set_tenant_id(tenant_id). set_config()
    zet alleen de PostgreSQL session-variabele (RLS), maar activeert de ADR-004
    do_orm_execute ContextVar-hook niet. Hierdoor mist de Python-laag de
    tenant-context en werkt multi-tenant filtering niet in alle code-paden.
    """
    src = (_REPO_ROOT / "src/core/copilot/audit/report_jobs.py").read_text(encoding="utf-8")

    uses_set_config = "set_config" in src
    uses_set_tenant_id = "set_tenant_id" in src

    assert not (uses_set_config and not uses_set_tenant_id), (
        "TI-002 (SP-DLP-001): report_jobs.py gebruikt set_config() maar niet "
        "set_tenant_id(). De PostgreSQL session-variabele wordt gezet (RLS actief) "
        "maar de Python ContextVar niet (ADR-004 ORM hook mist tenant-context). "
        "Vervang set_config() door set_tenant_id(tenant_id) in "
        "_generate_audit_report_async()."
    )
