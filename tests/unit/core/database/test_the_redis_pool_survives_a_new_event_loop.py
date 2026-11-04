"""De Redis-pool moet een nieuwe event loop overleven (ADR-036 OP-156).

`src/core/database/redis.py` hield de connectiepool in een module-globale variabele. Zo'n
pool hoort bij de event loop die draaide toen hij werd aangemaakt: de sockets erin zijn aan
die loop geregistreerd. Elke volgende loop krijgt een pool die aan een dode loop vastzit.

Gereproduceerd 2026-08-16 in drie regels, zonder enige wijziging aan de betrokken code:

    asyncio.run(get_redis_client())   -> ok
    asyncio.run(get_redis_client())   -> RuntimeError: Event loop is closed

pytest-asyncio maakt per test een nieuwe loop. In de volledige suite kwam dit boven als
`RuntimeError: Task ... got Future attached to a different loop` in een WILLEKEURIGE andere
test -- gezien in `tests/unit/workflow/test_workflow_real_routing.py`, die los gewoon
slaagt. Welke test valt hangt af van de xdist-verdeling.

**Waarom dit uiteindelijk is gerepareerd en niet alleen geregistreerd.** Als P2-bevinding
leek het een randgeval. Maar op 2026-08-17 viel hij in DRIE van de vier volledige runs, en
daarmee blokkeerde hij elke merge: een suite die drie op de vier keer rood is, is geen
poort meer maar een muntworp. Dat maakt hem in de praktijk zwaarder dan zijn label.

Het herstelpad dat er al stond (`_redis_pool = None` bij een mislukte ping) hielp niet: dat
vangt alleen `redis.ConnectionError` en `redis.TimeoutError`. De loop-mismatch is een
`RuntimeError` en glipte er langs.

**Mutatiebewijs (2026-08-17), beide richtingen:**
- De loop-controle uit `get_redis_client()` gehaald -> `test_a_second_event_loop_gets_a_
  working_client` ROOD met `Event loop is closed`.
- De controle omgekeerd (altijd een nieuwe pool) -> `test_the_same_loop_reuses_its_pool`
  ROOD. Zonder die helft zou "maak altijd een verse pool" een geldige oplossing zijn, en
  dan is het poolen zelf weg: elke aanroep bouwt dan verbindingen op en af.
- Ongewijzigd -> GROEN.
"""

from __future__ import annotations

import asyncio
import os
import socket

import pytest


def _redis_bereikbaar() -> bool:
    poort = int(os.environ.get("REDIS_PORT", "6380"))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        return s.connect_ex(("127.0.0.1", poort)) == 0


pytestmark = [
    pytest.mark.skipif(
        not _redis_bereikbaar(),
        reason="vereist Redis op REDIS_PORT (standaard 6380)",
    ),
    # OP-175-nazorg (2026-09-11): poort 6380 is uit POORTEN_MET_GEDATEERDE_UITZONDERING
    # gehaald, en deze test verbindt DOELBEWUST echt -- hij test het pool/event-loop-gedrag
    # zelf, niet een endpoint dat toevallig Redis raakt. Mocken zou precies wegnemen wat
    # hier bewezen wordt. Zonder deze marker gaat hij op de globale blokkade ROOD i.p.v.
    # SKIPPED zodra Redis lokaal bereikbaar is (gemeten: EchteVerbindingInUnitTest naar
    # ('::1', 6380, 0, 0), i.p.v. de bedoelde skip-op-onbereikbaarheid hierboven).
    pytest.mark.echte_netwerkverbinding_toegestaan,
]


def _haal_client_op() -> str:
    """Vraag een client op in een VERSE event loop en geef het pool-identiteitsbewijs terug.

    `asyncio.run` maakt een nieuwe loop en sluit hem daarna. Twee opeenvolgende aanroepen
    zijn dus twee verschillende loops -- precies de situatie die pytest-asyncio per test
    creeert.
    """

    async def binnen() -> str:
        from src.core.database import redis as redis_module

        client = await redis_module.get_redis_client()
        await client.ping()
        return str(id(client.connection_pool))

    return asyncio.run(binnen())


@pytest.mark.unit
def test_a_second_event_loop_gets_a_working_client() -> None:
    """De kern: een tweede loop krijgt een bruikbare client in plaats van een fout."""
    eerste = _haal_client_op()
    tweede = _haal_client_op()

    assert eerste and tweede, "geen pool gekregen"
    assert eerste != tweede, (
        "Beide loops kregen dezelfde pool. Die hoort bij de eerste loop, die inmiddels "
        "gesloten is; de tweede aanroep zou daarop stukgaan zodra hij de verbinding echt "
        "gebruikt."
    )


@pytest.mark.unit
def test_the_same_loop_reuses_its_pool() -> None:
    """De tegenrichting: binnen EEN loop wordt de pool wel hergebruikt.

    Zonder deze helft zou "maak altijd een verse pool" de test hierboven halen, en dan is
    het poolen zelf weg -- elke aanroep bouwt dan verbindingen op en weer af.
    """

    async def twee_keer_in_dezelfde_loop() -> tuple[str, str]:
        from src.core.database import redis as redis_module

        een = await redis_module.get_redis_client()
        twee = await redis_module.get_redis_client()
        return str(id(een.connection_pool)), str(id(twee.connection_pool))

    eerste, tweede = asyncio.run(twee_keer_in_dezelfde_loop())

    assert eerste == tweede, (
        f"Binnen dezelfde event loop kreeg de tweede aanroep een ANDERE pool "
        f"({eerste} tegen {tweede}). Dan wordt er niet gepoold en bouwt elke aanroep zijn "
        "eigen verbindingen op."
    )
