"""TODO(SP-MIG-ARCH-1): live Alembic-keten kan audit_logs niet vanaf een lege DB bootstrappen.

Ontdekt tijdens AUDIT-ARCH-2026-07-02 Dag 3 Groep D-verificatie: `alembic upgrade head`
tegen een volledig lege PostgreSQL-database faalt op
`0092fdf7d725_add_audit_log_hash_chain_fields.py` met
`UndefinedTable: relation "audit_logs" does not exist` (ALTER TABLE audit_logs ADD
COLUMN audit_hash).

Root cause: de enige migratie die ooit `audit_logs` aanmaakte is
`src/alembic/versions/archive/fix_audit_logs_table.py` -- gearchiveerd (dus buiten de
live keten) EN de create_table-aanroep daarin was al voor archivering uitgecommentarieerd
tot een no-op (`pass`) binnen de `if not insp.has_table("audit_logs")`-branch. Elke
bestaande omgeving (prod/staging/dev) overleeft dit omdat de tabel er al staat uit een
oudere bootstrap (voor Alembic, of via `scripts/create_schema_baseline.py`, zelf ook
verouderd -- stampt naar `merge_20260113`, ver voor de huidige head). Een echte
disaster-recovery-restore of gloednieuwe omgeving vanaf een lege DB zou hier vastlopen.

Niet binnen scope van SP-DATA-ARCH-1 (Groep D) -- dat betrof tenant_id-hardening op
experiments/notifications, geen keten-archeologie. Vereist een nieuwe live migratie die
`audit_logs` daadwerkelijk aanmaakt op de juiste plek in de keten (voor
0092fdf7d725), met een schema dat overeenkomt met `src/core/models/audit_log.py`.
"""

import ast
from pathlib import Path

_VERSIONS_DIR = Path("src/alembic/versions")


def _live_migration_creates_audit_logs_table() -> bool:
    """True als een live (niet-archive) migratie audit_logs daadwerkelijk aanmaakt."""
    for f in _VERSIONS_DIR.glob("*.py"):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8-sig", errors="ignore"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "create_table" and node.args:
                    try:
                        table_name = ast.literal_eval(node.args[0])
                    except Exception:
                        continue
                    if table_name == "audit_logs":
                        return True
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "execute" and node.args:
                    try:
                        sql = ast.literal_eval(node.args[0])
                    except Exception:
                        continue
                    if (
                        isinstance(sql, str)
                        and "CREATE TABLE" in sql.upper()
                        and "audit_logs" in sql
                    ):
                        return True
    return False


def test_live_migration_chain_can_bootstrap_audit_logs_from_empty_db() -> None:
    """TODO(SP-MIG-ARCH-1): live keten mist een echte CREATE TABLE audit_logs.

    Blijft rood totdat een live migratie (niet archive/) audit_logs daadwerkelijk
    aanmaakt v��r 0092fdf7d725_add_audit_log_hash_chain_fields.py in de keten.
    """
    assert _live_migration_creates_audit_logs_table(), (
        "Geen enkele live migratie in src/alembic/versions/ maakt audit_logs echt aan -- "
        "src/alembic/versions/archive/fix_audit_logs_table.py is gearchiveerd EN de "
        "create_table-aanroep daarin was al een no-op (pass) voor archivering. "
        "SP-MIG-ARCH-1: voeg een live migratie toe die audit_logs aanmaakt "
        "(schema volgens src/core/models/audit_log.py), geplaatst voor "
        "0092fdf7d725_add_audit_log_hash_chain_fields.py in de keten."
    )
