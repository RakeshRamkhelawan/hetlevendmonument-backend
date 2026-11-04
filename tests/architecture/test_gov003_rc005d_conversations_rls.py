"""Architecture test: conversations + conversation_messages moeten RLS hebben (RC-005d).

TODO(SP-GOV-003): add Alembic migration to enable RLS on conversations tables
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VERSIONS_DIR = _REPO_ROOT / "src/alembic/versions"


def test_conversations_rls_migration_exists() -> None:
    """RC-005d: actieve (non-archive) migratie MOET RLS aanzetten voor conversations."""
    found = any(
        "ENABLE ROW LEVEL SECURITY" in f.read_text(encoding="utf-8")
        and "conversations" in f.read_text(encoding="utf-8")
        for f in _VERSIONS_DIR.glob("*.py")
        if "archive" not in str(f)
    )
    assert found, (
        "RC-005d: geen actieve Alembic-migratie met ENABLE ROW LEVEL SECURITY "
        "voor de conversations tabel -- voeg 20260623_add_rls_conversations.py toe"
    )


def test_conversation_messages_rls_migration_exists() -> None:
    """RC-005d: actieve migratie MOET RLS aanzetten voor conversation_messages."""
    found = any(
        "ENABLE ROW LEVEL SECURITY" in f.read_text(encoding="utf-8")
        and "conversation_messages" in f.read_text(encoding="utf-8")
        for f in _VERSIONS_DIR.glob("*.py")
        if "archive" not in str(f)
    )
    assert found, (
        "RC-005d: geen actieve Alembic-migratie met ENABLE ROW LEVEL SECURITY "
        "voor de conversation_messages tabel"
    )
