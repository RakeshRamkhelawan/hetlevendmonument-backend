"""De critic-test laat de xdist-werker niet meer crashen (brief 2026-10-23, werker gw0).

Meting: `test_tenant_isolation_separate_critics` slaagt, maar de losse opslagtaak van de critic
(`CriticMixin._store_critique_async`) zit dan in `db_manager.get_session()` op een engine die een
EERDERE test in een inmiddels gesloten event loop heeft gemaakt (`DunningSkill` via
`_tel_openstaand`, en `test_core_agents_batch.py`). `asyncio.Runner` wacht bij het sluiten van de loop
op die taak, pytest-timeout doodt het proces, xdist meldt "worker crashed" op die test.
Reproductie: gw0's 6271 tests in volgorde, een proces, `--timeout=60` -> Timeout in
`_cancel_all_tasks`. De oorzaak en de reparatie staan in `tests/fixtures/db_manager_staat.py`.

MUTATIEBEWIJS (2026-10-23):
    de autouse-import uit `tests/unit/conftest.py` weghalen            -> `..._is_aangesloten` ROOD
    `herstel` laten return-en zonder terug te zetten                   -> `..._wordt_teruggezet` en
                                                                          `de_volgende_test_ziet...` ROOD
    legitiem: een test die `db_manager` niet aanraakt                  -> `..._blijft_onaangeroerd` GROEN
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests.fixtures.db_manager_staat import bewaar, herstel

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIT_CONFTEST = REPO_ROOT / "tests/unit/conftest.py"


def _manager(
    engine: object = None, maker: object = None, initialized: bool = False
) -> SimpleNamespace:
    return SimpleNamespace(engine=engine, async_session_maker=maker, _initialized=initialized)


def test_de_fixture_is_aangesloten_op_de_unittests() -> None:
    boom = ast.parse(UNIT_CONFTEST.read_text(encoding="utf-8"))
    geimporteerd = {
        alias.name
        for node in ast.walk(boom)
        if isinstance(node, ast.ImportFrom) and node.module == "tests.fixtures.db_manager_staat"
        for alias in node.names
    }

    assert "db_manager_blijft_zoals_hij_was" in geimporteerd


def test_een_door_de_test_gemaakte_engine_wordt_teruggezet() -> None:
    manager = _manager()
    voor = bewaar(manager)
    manager.engine = MagicMock()
    manager.async_session_maker = MagicMock()
    manager._initialized = True

    herstel(manager, voor)

    assert (manager.engine, manager.async_session_maker, manager._initialized) == (
        None,
        None,
        False,
    )


def test_de_weggegooide_engine_sluit_zijn_verbindingen_niet() -> None:
    manager = _manager()
    voor = bewaar(manager)
    nieuw = MagicMock()
    manager.engine = nieuw

    herstel(manager, voor)

    nieuw.sync_engine.dispose.assert_called_once_with(close=False)


def test_een_testdubbel_zonder_sync_engine_breekt_het_herstel_niet() -> None:
    manager = _manager()
    voor = bewaar(manager)
    manager.engine = SimpleNamespace()

    herstel(manager, voor)

    assert manager.engine is None


def test_een_test_die_alleen_de_vlag_wijzigt_wordt_teruggezet() -> None:
    manager = _manager(initialized=True)
    voor = bewaar(manager)
    manager._initialized = False

    herstel(manager, voor)

    assert manager._initialized is True


def test_een_voorafgaande_engine_blijft_onaangeroerd() -> None:
    oud = MagicMock()
    manager = _manager(engine=oud, maker=MagicMock(), initialized=True)
    voor = bewaar(manager)

    gewijzigd = herstel(manager, voor)

    assert (gewijzigd, manager.engine is oud) == (False, True)
    oud.sync_engine.dispose.assert_not_called()


_BEGIN: list[object] = []


def test_een_polluerende_test_zet_de_db_manager_vast() -> None:
    """Eerste helft van het paar: doet wat `DunningSkill` doet (zet een engine, laat hem staan)."""
    from src.core.database.database import db_manager

    _BEGIN.append(db_manager.engine)
    db_manager.engine = MagicMock()
    db_manager.async_session_maker = MagicMock()
    db_manager._initialized = True


def test_de_volgende_test_ziet_de_db_manager_zoals_hij_was() -> None:
    from src.core.database.database import db_manager

    if not _BEGIN:
        pytest.skip("de eerste helft van het paar draaide niet op deze werker")

    assert db_manager.engine is _BEGIN[0]
