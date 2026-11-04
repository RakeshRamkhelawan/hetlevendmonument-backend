"""Een echte `Request` voor tests die een limietroute rechtstreeks aanroepen.

De limietdecorators (`privacy_rate_limit` en de `*_limit` uit `governance/rate_limiter.py`) zoeken
een echte `starlette.requests.Request` tussen de argumenten. Een `MagicMock()` is er geen: de
limiet werd dan stilletjes overgeslagen, en de test oefende hem dus nooit uit. Sinds de nazorgbrief
van 2026-10-27 geeft een aanroep zonder `Request` een `RuntimeError`.

Elke aanroep krijgt een EIGEN clientadres, dus een eigen limietemmer: tests delen geen teller en
een test kan een andere niet in een 429 duwen.
"""

from __future__ import annotations

import itertools

from fastapi import Request

_teller = itertools.count(1)


def echte_request(
    headers: dict[str, str] | None = None, client_host: str | None = None
) -> Request:
    """Een anonieme `Request` met een uniek clientadres uit het documentatiebereik 198.51.x.y.

    `headers` en `client_host` voor een test die daar iets van afleest.
    """
    n = next(_teller)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (client_host or f"198.51.{(n // 250) % 250}.{n % 250 + 1}", 1000 + n % 60000),
    }
    return Request(scope=scope)  # type: ignore[arg-type]
