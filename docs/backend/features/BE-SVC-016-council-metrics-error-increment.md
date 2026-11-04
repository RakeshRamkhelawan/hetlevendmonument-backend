# BE-SVC-016: Council Metrics Error Increment

## Samenvatting

Voegt `COUNCIL_TURNS_TOTAL` counter increment toe aan de board/queue endpoint error handler. Dit maakt het mogelijk om board/queue errors te monitoren via Prometheus.

## Scope

- `src/core/api/v1/company/board_router.py`

## Wijzigingen

```python
from src.core.copilot.council.metrics import COUNCIL_TURNS_TOTAL

# In get_approval_queue exception handler:
COUNCIL_TURNS_TOTAL.labels(
    tenant_id=str(current_user.tenant_id),
    verdict="error",
).inc()
```

## Tests

- Handmatig verifieerbaar via `/metrics` endpoint na een forced error.

## ADR Impact

- ADR-014 (OpenTelemetry): Prometheus metrics voor council observability
- ADR-027 (Council/Copilot): error tracking op HITL/board endpoints

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)

> Elke error path in een council-gerelateerd endpoint moet een metric increment hebben. Dit maakt alerting mogelijk ("board queue error rate > 1%").
