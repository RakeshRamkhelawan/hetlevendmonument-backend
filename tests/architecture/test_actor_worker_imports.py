"""SP-WE-18: alle actor modules moeten geimporteerd zijn in actors.py."""

from pathlib import Path


def test_all_actor_modules_imported_in_worker() -> None:
    """SP-WE-18: worker entrypoint moet alle 5 actor modules importeren."""
    source = Path("src/workers/actors.py").read_text(encoding="utf-8")
    missing = []
    expected = [
        "integrity_check_actor",
        "cva_tasks",
        "contest_service",
        "report_jobs",
        "workflow_tasks",
    ]
    for module in expected:
        if module not in source:
            missing.append(module)
    assert not missing, (
        f"SP-WE-18: actor modules niet geimporteerd in actors.py: {missing}. "
        "Voeg side-effect imports toe zodat de worker de actors herkent."
    )
