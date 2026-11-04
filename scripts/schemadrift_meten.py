"""Meet de schemadrift (wat `alembic check` zou melden) en geef een telling per soort.

Alleen METEN: wijzigt geen model, geen migratie en geen data. Draait dezelfde stappen als
`alembic.command.check`, maar houdt de lijst met verschillen vast in plaats van alleen het
aantal te melden. De database waarop gemeten wordt komt uit `DATABASE_URL`; die moet al op
`head` staan (de aanroeper draait eerst `alembic upgrade head`).

Gebruik:
    DATABASE_URL=... python scripts/schemadrift_meten.py            # JSON met aantallen per soort
    DATABASE_URL=... python scripts/schemadrift_meten.py --lijst    # JSON met elke melding
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _vlak(diffs: list[object]) -> Iterator[tuple[object, ...]]:
    for d in diffs:
        if isinstance(d, list):
            yield from _vlak(d)
        else:
            assert isinstance(d, tuple)
            yield d


def meet_drift() -> list[dict[str, str | None]]:
    """Alle verschillen tussen `Base.metadata` en de database waar DATABASE_URL naar wijst."""
    sys.path.insert(0, str(REPO_ROOT))

    from alembic import autogenerate as autogen
    from alembic.config import Config
    from alembic.runtime.environment import EnvironmentContext
    from alembic.script import ScriptDirectory

    cfg = Config(str(REPO_ROOT / "src" / "alembic.ini"))
    script_directory = ScriptDirectory.from_config(cfg)
    args = {
        "message": None,
        "autogenerate": True,
        "sql": False,
        "head": "head",
        "splice": False,
        "branch_label": None,
        "version_path": None,
        "rev_id": None,
        "depends_on": None,
    }
    revision_context = autogen.RevisionContext(cfg, script_directory, args)

    def retrieve_migrations(rev: object, context: object) -> list[object]:
        revision_context.run_autogenerate(rev, context)  # type: ignore[arg-type]
        return []

    with EnvironmentContext(
        cfg,
        script_directory,
        fn=retrieve_migrations,  # type: ignore[arg-type]
        as_sql=False,
        template_args=revision_context.template_args,
        revision_context=revision_context,
    ):
        script_directory.run_env()

    diffs: list[object] = []
    for upgrade_ops in revision_context.generated_revisions[-1].upgrade_ops_list:
        diffs.extend(upgrade_ops.as_diffs())

    uit: list[dict[str, str | None]] = []
    for d in _vlak(diffs):
        op = str(d[0])
        rij: dict[str, str | None] = {"op": op, "tabel": None, "naam": None}
        if op in ("add_table", "remove_table"):
            rij["tabel"] = getattr(d[1], "name", None)
        elif op in ("add_column", "remove_column"):
            rij["tabel"], rij["naam"] = str(d[2]), getattr(d[3], "name", None)
        elif op in ("add_index", "remove_index", "add_fk", "remove_fk"):
            rij["tabel"] = getattr(getattr(d[1], "table", None), "name", None)
            rij["naam"] = getattr(d[1], "name", None)
        elif op in ("add_constraint", "remove_constraint"):
            rij["tabel"] = getattr(getattr(d[1], "table", None), "name", None)
            rij["naam"] = getattr(d[1], "name", None)
        elif op.startswith("modify_"):
            rij["tabel"], rij["naam"] = str(d[2]), str(d[3])
        uit.append(rij)
    return uit


def tel_per_soort(meldingen: list[dict[str, str | None]]) -> dict[str, int]:
    return dict(sorted(Counter(str(m["op"]) for m in meldingen).items()))


def main() -> None:
    meldingen = meet_drift()
    resultaat: object = meldingen if "--lijst" in sys.argv else tel_per_soort(meldingen)
    # Een markering vooraan de regel: alembic en de modelimport schrijven zelf ook naar stdout.
    print("SCHEMADRIFT_JSON " + json.dumps(resultaat))


if __name__ == "__main__":
    main()
