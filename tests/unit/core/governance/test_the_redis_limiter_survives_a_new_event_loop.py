"""De Redis-rate-limiter moet een nieuwe event loop overleven (ADR-036 OP-156).

`src/core/governance/rate_limiter.py::_get_redis_limiter()` cachete de `RedisRateLimiter` en
zijn `asyncio.Lock()` in module-globale variabelen -- exact hetzelfde patroon als de
connectiepool in `src/core/database/redis.py` (zie
`tests/unit/core/database/test_the_redis_pool_survives_a_new_event_loop.py`), en met dezelfde
gevolgen: de gecachete limiter houdt een Redis-client vast die aan de loop hangt waarin hij is
aangemaakt, en het slot weigert elke andere loop nadat het voor het eerst is gebruikt.

**Mutatiebewijs (2026-08-26), beide richtingen:**
- `_vervang_de_limiter_bij_een_nieuwe_loop()`-aanroep uit `_get_redis_limiter()` gehaald ->
  `test_a_second_event_loop_gets_a_working_limiter` ROOD (`RuntimeError` uit het slot dat aan
  de eerste, inmiddels gesloten loop hangt).
- De controle omgekeerd (altijd een nieuwe limiter) -> `test_the_same_loop_reuses_its_limiter`
  ROOD. Zonder die helft zou "maak altijd een verse limiter" een geldige oplossing zijn, en
  dan initialiseert elke aanroep opnieuw een Redis-client.
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


pytestmark = pytest.mark.skipif(
    not _redis_bereikbaar(),
    reason="vereist Redis op REDIS_PORT (standaard 6380)",
)


def _reset_module_state() -> None:
    """Begin elke test met een schone lei -- geen limiter uit een vorige test in dit proces."""
    from src.core.governance import rate_limiter as rate_limiter_module

    rate_limiter_module._redis_rate_limiter = None
    rate_limiter_module._redis_limiter_loop = None
    rate_limiter_module._redis_limiter_lock = asyncio.Lock()


def _haal_limiter_op() -> str:
    """Vraag de limiter op in een VERSE event loop en geef zijn identiteit terug.

    `asyncio.run` maakt een nieuwe loop en sluit hem daarna. Twee opeenvolgende aanroepen
    zijn dus twee verschillende loops -- precies de situatie die pytest-asyncio per test
    creeert.
    """

    async def binnen() -> str:
        from src.core.governance.rate_limiter import _get_redis_limiter

        limiter = await _get_redis_limiter()
        return str(id(limiter))

    return asyncio.run(binnen())


@pytest.mark.unit
def test_a_second_event_loop_gets_a_working_limiter() -> None:
    """De kern: een tweede loop krijgt een bruikbare limiter in plaats van een RuntimeError."""
    _reset_module_state()
    eerste = _haal_limiter_op()
    tweede = _haal_limiter_op()

    assert eerste and eerste != "None", "geen limiter gekregen (Redis onbereikbaar in de test?)"
    assert eerste != tweede, (
        "Beide loops kregen dezelfde limiter. Die hoort bij de eerste loop, die inmiddels "
        "gesloten is; de tweede aanroep zou daarop stukgaan zodra de onderliggende client "
        "echt wordt gebruikt."
    )


@pytest.mark.unit
def test_the_same_loop_reuses_its_limiter() -> None:
    """De tegenrichting: binnen EEN loop wordt de limiter wel hergebruikt.

    Zonder deze helft zou "maak altijd een verse limiter" de test hierboven halen, en dan
    initialiseert elke aanroep zijn eigen Redis-client opnieuw.
    """
    _reset_module_state()

    async def twee_keer_in_dezelfde_loop() -> tuple[str, str]:
        from src.core.governance.rate_limiter import _get_redis_limiter

        een = await _get_redis_limiter()
        twee = await _get_redis_limiter()
        return str(id(een)), str(id(twee))

    eerste, tweede = asyncio.run(twee_keer_in_dezelfde_loop())

    assert eerste == tweede, (
        f"Binnen dezelfde event loop kreeg de tweede aanroep een ANDERE limiter "
        f"({eerste} tegen {tweede}). Dan wordt er niet gecachet en initialiseert elke "
        "aanroep zijn eigen Redis-client."
    )
