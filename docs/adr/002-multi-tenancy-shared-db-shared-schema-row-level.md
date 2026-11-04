# ADR-002: Multi-tenancy Model - Shared Database + Shared Schema

## Status
Accepted

## Context
SanskritiSetu moet honderden culturele instellingen ondersteunen met een beperkt infra-budget. De architectuur moet schaalbaar zijn van 1 naar 1000+ tenants zonder lineaire groei van beheerkosten.

### Eisen
1. **Kosten**: Lage infra-footprint (geen redundante DB processen).
2. **Isolatie**: Strikte scheiding; tenant A mag nooit data van tenant B zien.
3. **Analytics**: Mogelijkheid tot (geautoriseerde) cross-tenant aggregatie voor overkoepelende culturele trends.

### Alternatieven
| Model | Voordeel | Nadeel | Besluit |
| :--- | :--- | :--- | :--- |
| **DB per Tenant** | Maximale isolatie | Zeer duur; complexe migraties | **Afgewezen** |
| **Schema per Tenant** | Goede balans | Postgres performance issues bij >500 schema's | **Afgewezen** |
| **Shared Schema** | Goedkoop; snel | Risico op "forgotten filters" | **Geselecteerd** |

## Decision
We hanteren het **Shared Database, Shared Schema** model. Elke tabel met tenant-data bevat een `tenant_id` kolom (UUID).

### Noisy Neighbor Mitigatie (SLI/SLO)
Om te voorkomen dat één tenant de infra blokkeert, hanteren we de volgende SLO's per tenant-flow:
| Metriek | SLI | SLO Target |
| :--- | :--- | :--- |
| **Query Latency** | p99 van tenant-scoped SELECT | < 200ms |
| **Resource Usage** | CPU/Memory per tenant-request | < 10% van totale cluster capaciteit |

### Handhaving
Hierarchie van guards:
1. **Middleware**: JWT extractie (ADR-003).
2. **ORM**: Automatische query injectie (ADR-004).
3. **DB**: NOT NULL constraints op `tenant_id` (ADR-005).

## Consequences
- **Positive**:
    - Zeer lage kosten per tenant.
    - Één enkele database-migratie voor het hele platform.
- **Negative**:
    - **Risico**: Eén foutieve query in raw SQL kan alle data lekken.
    - **Operationele Last**: Vereist nauwkeurige monitoring van tenant-belasting via Prometheus labels (`tenant_id`).
- **Degrade Mode**:
    - Bij database-overbelasting: "Reject new requests" voor de zwaarst belastende tenants (circuit breaker) gebaseerd op real-time metrics.
