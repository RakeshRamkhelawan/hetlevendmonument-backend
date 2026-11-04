"""AUDIT-FIND-002: CVA autonomous trigger mag geen subprocess aanroepen."""

import ast
from pathlib import Path


CVA_FILE = Path("src/core/agents/cva_autonomous_trigger.py")


def test_cva_breakthrough_contains_no_subprocess_run() -> None:
    """subprocess.run call is verwijderd uit AST (AUDIT-FIND-002).

    Controleert via AST, niet string-search, zodat comments geen false positive geven.
    """
    tree = ast.parse(CVA_FILE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # subprocess.run(...)
            if isinstance(func, ast.Attribute) and func.attr == "run":
                if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                    raise AssertionError(
                        f"cva_autonomous_trigger.py bevat nog subprocess.run op regel {node.lineno} -- AUDIT-FIND-002"
                    )


def test_cva_breakthrough_contains_no_subprocess_import() -> None:
    """subprocess-import mag niet meer in _run_cva_breakthrough staan."""
    tree = ast.parse(CVA_FILE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "subprocess", (
                    "cva_autonomous_trigger.py importeert nog subprocess -- AUDIT-FIND-002"
                )
        if isinstance(node, ast.ImportFrom):
            assert node.module != "subprocess", (
                "cva_autonomous_trigger.py importeert nog subprocess -- AUDIT-FIND-002"
            )


def test_cva_breakthrough_returns_failure_without_subprocess() -> None:
    """_run_cva_breakthrough geeft structured failure terug zonder subprocess."""
    from src.core.agents.cva_autonomous_trigger import CVAAutonomousTrigger

    trigger = CVAAutonomousTrigger.__new__(CVAAutonomousTrigger)
    result = trigger._run_cva_breakthrough({})
    assert result["success"] is False
    assert "error" in result
    assert "execution_time" in result
