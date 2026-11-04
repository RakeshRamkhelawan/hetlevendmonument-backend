"""backend-patterns.md #9 -- NOOIT sa.inspect(op.get_bind()) in migrations.

Discovered 2026-07-02 (Sprint Dag 1 Groep 4, independent Final Approver review):
migration 884d744f6aa9 originally used `sa.inspect(op.get_bind())` to guard
`op.create_table()` calls with a has_table() check. This crashes during an offline
dry-run (`alembic upgrade head --sql`, used by scripts/pre-deploy-check.sh) with
`sqlalchemy.exc.NoInspectionAvailable: No inspection system is available for object
of type <class 'sqlalchemy.engine.mock.MockConnection'>` -- a real, reproducible
deploy-blocker, not a style nitpick. Fixed by switching to raw
"CREATE TABLE IF NOT EXISTS"/"DROP TABLE IF EXISTS" SQL (matches the established
pattern in 20260404_gdpr_tables.py). This test guards against reintroducing the
pattern in any live (non-archive) migration.
"""

import ast
from pathlib import Path

_LIVE_MIGRATIONS_DIR = Path("src/alembic/versions")


def _is_sa_inspect_of_get_bind(node: ast.AST) -> bool:
    """Matches sa.inspect(op.get_bind()) or inspect(op.get_bind()) -- inspecting the
    live bind, which is unavailable during an offline dry-run."""
    if not (isinstance(node, ast.Call) and node.args):
        return False
    func = node.func
    is_inspect_call = (isinstance(func, ast.Attribute) and func.attr == "inspect") or (
        isinstance(func, ast.Name) and func.id == "inspect"
    )
    if not is_inspect_call:
        return False
    arg = node.args[0]
    return (
        isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "get_bind"
    )


def test_no_live_migration_inspects_the_bind() -> None:
    violations = []
    fouten: list[str] = []
    gescand = 0
    migration_files = list(_LIVE_MIGRATIONS_DIR.glob("*.py"))
    for migration_file in migration_files:
        try:
            tree = ast.parse(migration_file.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            fouten.append(f"{migration_file.name}: {exc}")
            continue
        gescand += 1
        for node in ast.walk(tree):
            if _is_sa_inspect_of_get_bind(node):
                violations.append(migration_file.name)
                break

    assert len(migration_files) > 10, (
        f"Slechts {len(migration_files)} bestanden gevonden in {_LIVE_MIGRATIONS_DIR} -- "
        "dat lijkt een (bijna) lege map. Verkeerd pad? Deze guard controleert dan "
        "vrijwel niets."
    )
    assert not fouten, (
        "Deze migraties konden niet gelezen/geparsed worden en zijn NIET gecontroleerd "
        f"op sa.inspect(op.get_bind()) (gescand: {gescand}):\n"
        + "\n".join(f"  - {f}" for f in fouten)
    )
    assert not violations, (
        f"backend-patterns.md #9 violation -- these live migrations call "
        f"sa.inspect(op.get_bind()), which crashes during an offline dry-run "
        f"(alembic upgrade head --sql, used by scripts/pre-deploy-check.sh): "
        f"{violations}. Use raw 'CREATE TABLE IF NOT EXISTS' SQL instead."
    )
