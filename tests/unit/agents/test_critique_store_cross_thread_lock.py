"""CritiqueStore._lock moet echte wederzijdse uitsluiting geven over dramatiq-workerthreads
heen (ADR-036 OP-16).

**De bevinding, empirisch gemeten (2026-08-27), niet aangenomen.** `asyncio.Lock` bindt zich
niet aan een loop bij AANMAKEN (Python 3.10+, gemeten op 3.13) -- SEQUENTIEEL hergebruik over
loops heen (bv. pytest die per test een nieuwe loop maakt) werkt daardoor prima. Maar bij
GELIJKTIJDIG gebruik vanuit twee ECHTE event loops in twee verschillende threads hangt de
TWEEDE loop voor altijd op de acquire, gemeten met twee daemon-threads en een `join(timeout=...)`.

Dat is precies dramatiq's threadingmodel: `docker-compose.yml`'s `workflow-worker` draait met
`--threads 4`, `learning-worker` met `--threads 2`. `CritiqueStore` wordt bereikt via
`CriticMixin` -> `EnhancedBaseAgent`, dus agent-uitvoering vanuit meerdere workerthreads kan
`store._lock` (en de negen gebruiksplekken die erop leunen) gelijktijdig raken.

**De fix.** `threading.Lock` in plaats van `asyncio.Lock`. Geen van de negen kritieke secties
bevat een `await` (geverifieerd met een AST-scan), dus een korte, synchrone `with self._lock:`
binnen een `async def`-methode blokkeert de event loop nooit langer dan de in-memory
dict-mutatie zelf kost. `threading.Lock` heeft geen loop-binding-probleem, dus mag WEL gewoon
eager op class-niveau staan -- de AST-guard in
`tests/architecture/test_no_import_time_asyncio_primitives.py` scant specifiek op
`asyncio.Lock/Event/Queue/Semaphore/BoundedSemaphore/Condition` en laat `threading.Lock`
terecht met rust.

**Waarom rechtstreeks op `store._lock` en niet via `clear_tenant()`.** Een eerdere versie
injecteerde de kunstmatige vertraging via `unittest.mock.patch` op `logger.info` -- die patch
is GLOBALE staat, niet thread-lokaal, en raakte daardoor ook thread B's eigen aanroep. Dat gaf
een test die faalde om een reden die niets met de lock te maken had. Deze versie omzeilt de
businesslogica volledig en oefent alleen het lock-object zelf uit, met threading.Event voor
deterministische synchronisatie in plaats van een slaap-gok.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from src.core.agents.critique_store import CritiqueStore


@pytest.fixture(autouse=True)
def reset_critique_store():
    CritiqueStore._instance = None
    yield
    CritiqueStore._instance = None


@pytest.mark.unit
def test_the_lock_provides_mutual_exclusion_across_two_concurrent_event_loops() -> None:
    """Twee ECHTE event loops in twee threads proberen `store._lock` gelijktijdig te
    verwerven. Thread A houdt hem vast tot thread B daadwerkelijk heeft geprobeerd te
    verwerven (gesynchroniseerd via `threading.Event`, geen slaap-gok); thread B mag pas
    verzilveren NADAT A loslaat -- nooit ertussenin, en zonder permanent te hangen.
    """
    store = CritiqueStore()

    order: list[str] = []
    a_holds = threading.Event()
    b_tried = threading.Event()

    def run_a() -> None:
        async def _go() -> None:
            with store._lock:
                order.append("A-acquired")
                a_holds.set()
                # Wacht tot B daadwerkelijk heeft geprobeerd te verwerven voor A loslaat --
                # zonder dit zou A altijd al klaar kunnen zijn voor B ook maar begint.
                b_tried.wait(timeout=3)
                order.append("A-released")

        asyncio.run(_go())

    def run_b() -> None:
        async def _go() -> None:
            a_holds.wait(timeout=3)
            order.append("B-trying")
            b_tried.set()
            with store._lock:
                order.append("B-acquired")

        asyncio.run(_go())

    thread_a = threading.Thread(target=run_a, daemon=True)
    thread_b = threading.Thread(target=run_b, daemon=True)

    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=5)
    thread_b.join(timeout=5)

    assert not thread_a.is_alive(), "Thread A is blijven hangen"
    assert not thread_b.is_alive(), (
        "Thread B is blijven hangen -- asyncio.Lock geeft geen wederzijdse uitsluiting "
        "tussen twee event loops in twee threads."
    )
    assert order == ["A-acquired", "B-trying", "A-released", "B-acquired"], (
        f"Verkeerde volgorde: {order}. B mag pas verwerven NADAT A loslaat -- deze uitkomst "
        "betekent dat er geen echte wederzijdse uitsluiting was."
    )
