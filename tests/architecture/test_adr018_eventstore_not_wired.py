"""AUDIT-ARCH-2026-07-02 Dag 2 losse P1 -- ARCH-002 /
arch-adr018-status-drift-orphan-eventstore.

ADR-018's status stond op "Accepted" terwijl `EventStore` nergens in live code
geimporteerd/geinstantieerd wordt (CLAUDE.md's kernbeslissingen-tabel claimde al
"Post-MVP" -- de ADR-header was niet gesynchroniseerd). Dit is nu gecorrigeerd
naar "Post-MVP".

Deze test bewaakt de consistentie: zodra `EventStore` wel in een live (niet-test,
niet-archive) import-pad terechtkomt, faalt deze test totdat de ADR-018-status
opnieuw wordt bijgewerkt naar "Accepted"/"Actief" -- zo kan de documentatie niet
stilzwijgend weer uit sync raken met de werkelijke code-status.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EVENT_STORE_MODULE = "src.core.als.enterprise.events.event_store"
ADR_018_PATH = REPO_ROOT / "docs" / "adr" / "018-event-sourcing-immutable-log.md"


def _live_python_files() -> list[Path]:
    src_root = REPO_ROOT / "src"
    return [
        p
        for p in src_root.rglob("*.py")
        if "archive" not in p.parts
        and p != src_root / "core" / "als" / "enterprise" / "events" / "event_store.py"
        and p.name != "__init__.py"
    ]


def _imports_event_store(py_file: Path) -> bool:
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8-sig"), filename=str(py_file))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and EVENT_STORE_MODULE in node.module:
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if EVENT_STORE_MODULE in alias.name:
                    return True
    return False


def test_eventstore_is_not_wired_into_live_code() -> None:
    """Zolang deze test GROEN is, klopt de ADR-018-status 'Post-MVP'. Als iemand
    EventStore alsnog bedraadt, moet ADR-018 eerst naar 'Accepted' worden gezet."""
    wired_in = [
        str(p.relative_to(REPO_ROOT)) for p in _live_python_files() if _imports_event_store(p)
    ]
    assert not wired_in, (
        f"EventStore wordt nu geimporteerd in live code: {wired_in}. "
        "Update docs/adr/018-event-sourcing-immutable-log.md status naar "
        "'Accepted' (dit is een bewuste activatie, geen regressie)."
    )


def test_adr018_status_is_post_mvp() -> None:
    content = ADR_018_PATH.read_text(encoding="utf-8")
    status_section = content.split("## Status", 1)[1].split("##", 1)[0]
    assert "Post-MVP" in status_section, (
        "ADR-018 status-header is niet 'Post-MVP' terwijl EventStore niet gewired "
        "is -- synchroniseer de status met de werkelijke code-status."
    )
