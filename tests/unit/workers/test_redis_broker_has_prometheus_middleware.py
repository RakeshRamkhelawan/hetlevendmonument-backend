"""Het gedeployde broker heeft Prometheus-metrics (ADR-014), zonder ze zelf te registreren.

`src/core/workflow/worker.py` probeerde `Prometheus`-middleware EXPLICIET toe te voegen en
had daarbij een importfout (OP-11-follow-up, gemeten 2026-07-31) -- maar die module is
inmiddels verwijderd als bevestigd dode code (ADR-036 OP-158 D2b). Het echte, gedeployde
`src/workers/workflow_worker.py::get_redis_broker()` voegt NOOIT expliciet `Prometheus` toe.

Dit is geen gat: dramatiq's `RedisBroker()` registreert `Prometheus` als onderdeel van zijn
DEFAULT middleware-set, gemeten hier direct op het geconstrueerde object -- niet aangenomen
uit dramatiq's documentatie.
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_the_deployed_broker_has_prometheus_middleware() -> None:
    from dramatiq.middleware.prometheus import Prometheus

    from src.workers.workflow_worker import get_redis_broker

    broker = get_redis_broker()

    assert any(isinstance(m, Prometheus) for m in broker.middleware), (
        "De gedeployde broker heeft geen Prometheus-middleware -- Dramatiq queue/latency-"
        "metrics (ADR-014) ontbreken dan stil."
    )
