"""Migratie: bestaande ondernemingen krijgen de vier-ogen-standaard (ADR-039, Rakesh 2026-10-05).

Op ECHTE PostgreSQL, in een eigen wegwerpdatabase die deze module aanmaakt en weer weggooit. De
server komt uit `SANSKRITISETU_TEST_DATABASE_URL` (nooit geraden, zie `tests/fixtures/testdatabase.py`).
Alleen een minimale `tenants`-tabel met de echte kolomvorm (`settings json`, mag NULL), zodat de
test de migratiefuncties zelf draait en niet de hele keten.

Wat vastligt:
- een tenant ZONDER sleutel krijgt de standaard, de uitlegmarkering en het migratiemerkteken;
- een tenant MET eigen instelling (ook een lege lijst) blijft byte-voor-byte gelijk;
- `downgrade()` zet precies terug wat er stond, ook NULL; en upgrade daarna werkt opnieuw;
- een tenant die na de upgrade zelf koos (merkteken weg) wordt door downgrade niet aangeraakt.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from tests.fixtures.testdatabase import testdatabase_url

MIGRATIE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "alembic"
    / "versions"
    / "20261007_vier_ogen_bestaande_tenants.py"
)

STANDAARD = [
    "query_hr_database",
    "analyze_skill_gap",
    "schedule_training",
    "make_payment",
    "change_iban",
    "write_off_receivable",
    "transfer_to_debt_collection",
]

pytestmark = [pytest.mark.integration]


def _laad_migratie() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vier_ogen_migratie", MIGRATIE)
    assert spec is not None and spec.loader is not None, f"migratie ontbreekt: {MIGRATIE}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def engine() -> Iterator[sa.Engine]:
    naam = f"vier_ogen_wegwerp_{uuid.uuid4().hex[:8]}"
    beheer = sa.create_engine(
        testdatabase_url(database="postgres", sync=True), isolation_level="AUTOCOMMIT"
    )
    with beheer.connect() as c:
        c.execute(sa.text(f'CREATE DATABASE "{naam}"'))
    eng = sa.create_engine(testdatabase_url(database=naam, sync=True))
    with eng.begin() as c:
        c.execute(
            sa.text(
                "CREATE TABLE tenants (id integer PRIMARY KEY, name varchar(255) NOT NULL, "
                "slug varchar(100) NOT NULL, settings json)"
            )
        )
        rijen = [
            (1, None),
            (2, json.dumps({})),
            (3, json.dumps({"theme": "dark"})),
            (4, json.dumps({"four_eyes_actions": ["make_payment"], "theme": "licht"})),
            (5, json.dumps({"four_eyes_actions": []})),
            (6, json.dumps(["geen", "object"])),
            # Een merkteken van een ANDERE revisie: niet van deze migratie, dus niet terugdraaien.
            (
                7,
                json.dumps(
                    {
                        "four_eyes_actions": ["make_payment"],
                        "four_eyes_set_by_migration": {"revision": "een_andere_revisie"},
                    }
                ),
            ),
        ]
        for tid, settings in rijen:
            c.execute(
                sa.text(
                    "INSERT INTO tenants (id, name, slug, settings) "
                    "VALUES (:id, :n, :n, CAST(:s AS json))"
                ),
                {"id": tid, "n": f"t{tid}", "s": settings},
            )
    try:
        yield eng
    finally:
        eng.dispose()
        with beheer.connect() as c:
            c.execute(sa.text(f'DROP DATABASE IF EXISTS "{naam}" WITH (FORCE)'))
        beheer.dispose()


def _draai(eng: sa.Engine, richting: str) -> None:
    module = _laad_migratie()
    with eng.begin() as c:
        ctx = MigrationContext.configure(c)
        with Operations.context(ctx):
            getattr(module, richting)()


def _settings(eng: sa.Engine) -> dict[int, object]:
    with eng.connect() as c:
        rijen = c.execute(sa.text("SELECT id, settings::text FROM tenants ORDER BY id")).all()
    return {r[0]: (json.loads(r[1]) if r[1] is not None else None) for r in rijen}


def _tekst(eng: sa.Engine) -> dict[int, str | None]:
    with eng.connect() as c:
        rijen = c.execute(sa.text("SELECT id, settings::text FROM tenants ORDER BY id")).all()
    return {r[0]: r[1] for r in rijen}


def test_a_tenant_without_the_setting_gets_the_default(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")

    s = _settings(engine)[3]

    assert isinstance(s, dict) and s["four_eyes_actions"] == STANDAARD


def test_the_rest_of_settings_is_kept(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")

    s = _settings(engine)[3]

    assert isinstance(s, dict) and s["theme"] == "dark"


def test_a_migrated_tenant_is_marked_to_see_the_explanation(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")

    s = _settings(engine)[1]

    assert isinstance(s, dict) and s["four_eyes_explanation_pending"] is True


def test_a_tenant_with_its_own_setting_is_untouched(engine: sa.Engine) -> None:
    voor = _tekst(engine)

    _draai(engine, "upgrade")

    na = _tekst(engine)
    assert (na[4], na[5], na[6]) == (voor[4], voor[5], voor[6])


def test_downgrade_restores_exactly_what_was_there(engine: sa.Engine) -> None:
    voor = _settings(engine)
    _draai(engine, "upgrade")

    _draai(engine, "downgrade")

    assert _settings(engine) == voor


def test_upgrade_after_downgrade_sets_the_default_again(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")
    _draai(engine, "downgrade")

    _draai(engine, "upgrade")

    s = _settings(engine)[2]
    assert isinstance(s, dict) and s["four_eyes_actions"] == STANDAARD


def test_downgrade_leaves_a_choice_made_after_the_upgrade(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")
    with engine.begin() as c:
        c.execute(
            sa.text(
                "UPDATE tenants SET settings = CAST(:s AS json) WHERE id = 3"
            ),
            {"s": json.dumps({"theme": "dark", "four_eyes_actions": ["make_payment"]})},
        )

    _draai(engine, "downgrade")

    assert _settings(engine)[3] == {"theme": "dark", "four_eyes_actions": ["make_payment"]}
