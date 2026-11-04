"""Een unittest laat de globale `db_manager` achter zoals hij hem aantrof.

Gemeten 2026-10-23 (brief werker-crasht-op-de-critic-test): `DunningSkill.execute_with_manifest_prompt`
(via `_tel_openstaand` en `ReceivablesToolRegistry`) en de tests in `test_core_agents_batch.py` zetten
de globale `db_manager` op `_initialized=True` met een engine die in de event loop van DIE test is
gemaakt. Die loop wordt na de test gesloten, de engine blijft staan. Een latere test die via
`db_manager.get_session()` iets doet -- hier de losse opslagtaak van de critic
(`CriticMixin._store_critique_async`, `asyncio.create_task`) -- krijgt dan een verbinding van een
gesloten loop. Bij het sluiten van de loop door pytest-asyncio wacht `asyncio.Runner` op die taak
(`_cancel_all_tasks`), de taak komt niet klaar, pytest-timeout (thread) doodt het proces en xdist
meldt "worker crashed" op de laatste test die de werker meldde.

De fixture legt de staat voor elke test vast en zet hem erna terug als de test hem heeft veranderd.
De nieuwe engine wordt weggegooid met `dispose(close=False)`: de verbindingen horen bij een gesloten
loop en kunnen niet meer netjes worden afgesloten.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest


@dataclass(frozen=True)
class DbManagerStaat:
    initialized: bool
    engine: Any
    async_session_maker: Any


def bewaar(manager: Any) -> DbManagerStaat:
    return DbManagerStaat(
        initialized=manager._initialized,
        engine=manager.engine,
        async_session_maker=manager.async_session_maker,
    )


def herstel(manager: Any, voor: DbManagerStaat) -> bool:
    """Zet de staat van voor de test terug; geeft True als er iets te herstellen viel."""
    if (
        manager.engine is voor.engine
        and manager.async_session_maker is voor.async_session_maker
        and manager._initialized == voor.initialized
    ):
        return False
    nieuw = manager.engine
    # Een testdubbel (`_Engine` in test_applicatierol_controle) heeft geen `sync_engine`: dan valt er
    # niets weg te gooien.
    sync_engine = getattr(nieuw, "sync_engine", None)
    if nieuw is not voor.engine and sync_engine is not None:
        sync_engine.dispose(close=False)
    manager.engine = voor.engine
    manager.async_session_maker = voor.async_session_maker
    manager._initialized = voor.initialized
    return True


@pytest.fixture(autouse=True)
def db_manager_blijft_zoals_hij_was() -> Iterator[None]:
    from src.core.database import database

    voor = bewaar(database.db_manager)
    yield
    herstel(database.db_manager, voor)
