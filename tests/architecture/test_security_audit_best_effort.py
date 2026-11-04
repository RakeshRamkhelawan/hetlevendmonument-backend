"""Architecture test: security_audit_service gebruikt best_effort voor DB writes."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
SERVICE_PATH = REPO_ROOT / "src/core/security/security_audit_service.py"


def _find_function(tree: ast.AST, func_name: str) -> ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == func_name:
            return node
    return None


def _uses_best_effort(func_node: ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(func_node):
        if isinstance(node, ast.AsyncWith):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call):
                    func = call.func
                    if isinstance(func, ast.Name) and func.id == "best_effort":
                        return True
                    if isinstance(func, ast.Attribute) and func.attr == "best_effort":
                        return True
    return False


def _audit_hash_inside_best_effort(func_node: ast.AsyncFunctionDef) -> bool:
    """Controleer dat audit_hash/previous_hash BINNEN de best_effort async-with body
    worden gezet (GOV-004, AUDIT-ARCH-2026-07-02 -- vervangt het verwijderde
    self._last_hash-patroon uit SP-DSM-001 met de canonieke HashChainVerifier-kolommen).

    Als de hash-chain-velden buiten de best_effort block bijgewerkt worden, corrumpeert
    de SHA-256 keten bij een mislukte DB-commit: de hash advances terwijl de rij nooit
    geschreven is.
    """
    for node in ast.walk(func_node):
        if not isinstance(node, ast.AsyncWith):
            continue
        uses_be = any(
            isinstance(item.context_expr, ast.Call)
            and (
                (
                    isinstance(item.context_expr.func, ast.Name)
                    and item.context_expr.func.id == "best_effort"
                )
                or (
                    isinstance(item.context_expr.func, ast.Attribute)
                    and item.context_expr.func.attr == "best_effort"
                )
            )
            for item in node.items
        )
        if not uses_be:
            continue
        for stmt in node.body:
            for sub in ast.walk(stmt):
                if isinstance(sub, ast.Assign):
                    for target in sub.targets:
                        if isinstance(target, ast.Attribute) and target.attr in (
                            "audit_hash",
                            "previous_hash",
                        ):
                            return True
    return False


def test_log_event_uses_best_effort():
    """log_event() MOET best_effort gebruiken voor audit DB write -- SP-DSM-001.

    Bare db.add() + await db.commit() zonder best_effort schendt backend-patterns.md 3.
    Audit log failures mogen nooit cascaderen naar callers.
    """
    src = SERVICE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = _find_function(tree, "log_event")
    assert func is not None, "log_event() niet gevonden in security_audit_service.py"
    assert _uses_best_effort(func), (
        "log_event() schrijft naar DB zonder best_effort context manager. "
        "Voeg 'async with best_effort(..., db_session=db):' toe rondom db.add() + await db.commit(). "
        "Zie backend-patterns.md 3 -- SP-DSM-001."
    )


def test_log_event_audit_hash_inside_best_effort():
    """audit_hash/previous_hash MOETEN binnen de best_effort body bijgewerkt worden --
    GOV-004 (AUDIT-ARCH-2026-07-02). Vervangt test_log_event_last_hash_inside_best_effort
    (SP-DSM-001): het oude self._last_hash-instantiestate-patroon is vervangen door de
    canonieke HashChainVerifier + audit_hash/previous_hash-kolommen.

    Als de hash-chain-velden buiten de best_effort block staan, advance de SHA-256 keten
    ook bij een mislukte DB-commit, wat hash-chain corruptie veroorzaakt.
    """
    src = SERVICE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = _find_function(tree, "log_event")
    assert func is not None, "log_event() niet gevonden in security_audit_service.py"
    assert _audit_hash_inside_best_effort(func), (
        "audit_hash/previous_hash worden BUITEN de best_effort block bijgewerkt. "
        "Verplaats de hash-chain-populatie naar binnen de 'async with best_effort(...)' body. "
        "Zie GOV-004."
    )


def test_create_alert_uses_best_effort():
    """_create_alert() MOET best_effort gebruiken voor alert DB write -- SP-DSM-001.

    Bare db.add() + await db.commit() zonder best_effort schendt backend-patterns.md 3.
    Alert creation failures mogen nooit cascaderen naar de security detection loop.
    """
    src = SERVICE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    func = _find_function(tree, "_create_alert")
    assert func is not None, "_create_alert() niet gevonden in security_audit_service.py"
    assert _uses_best_effort(func), (
        "_create_alert() schrijft naar DB zonder best_effort context manager. "
        "Voeg 'async with best_effort(..., db_session=db):' toe rondom db.add() + await db.commit(). "
        "Zie backend-patterns.md 3 -- SP-DSM-001."
    )
