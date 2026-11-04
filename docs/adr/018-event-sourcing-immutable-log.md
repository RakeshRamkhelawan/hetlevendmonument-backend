# ADR 018: Event Sourcing - Immutable Event Log

## Status
Post-MVP (ADR-019 audit-hash-chain voldoende voor launch)

`EventStore` (src/core/als/enterprise/events/event_store.py) is volledig
geimplementeerd conform dit ADR, maar wordt nergens geimporteerd of
geinstantieerd door live code (AUDIT-ARCH-2026-07-02, ARCH-002 /
arch-adr018-status-drift-orphan-eventstore). Deze status-header hield voorheen
"Accepted" aan terwijl de kernbeslissingen-tabel in CLAUDE.md al langer
"Post-MVP" claimde -- dit is nu gesynchroniseerd. Regressiebeveiliging:
tests/architecture/test_adr018_eventstore_not_wired.py faalt zodra `EventStore`
alsnog gewired wordt zonder deze status-header bij te werken.

## Context
Voor enterprise audit en debugging hebben we nodig:
- Complete history van alle state changes
- Mogelijkheid om state te reconstrueren op elk tijdstip
- Tamper-evident logging (bewijs dat logs niet zijn aangepast)
- Efficiente querying per aggregate (contract, agent, etc.)

Traditionele "current state" databases bieden dit niet.

## Decision
We implementeren **Event Sourcing** met een append-only event log:

1. **Immutable Events**: Events kunnen nooit worden gewijzigd of verwijderd
2. **Hash Chain**: Elk event bevat hash van vorige event (blockchain-achtig)
3. **State Projection**: Current state wordt berekend door events te "replayen"
4. **Partitioning**: Events worden gepartitioneerd op (tenant_id, maand) voor schaalbaarheid

### Event Schema
```
Event {
  event_id: UUID
  event_type: enum (CONTRACT_PROPOSED, AGREED, EXECUTING, etc.)
  aggregate_id: string (bijv. contract-001)
  aggregate_type: string (bijv. "contract")
  payload: JSON
  timestamp: datetime
  previous_hash: string
  event_hash: SHA256(previous_hash + payload)
}
```

### Storage Strategy
- **Hot data** (laatste 30 dagen): Redis + PostgreSQL
- **Warm data** (1-12 maanden): PostgreSQL
- **Cold data** (>12 maanden): S3/archive

## Consequences

### Positive
- Complete audit trail (wie, wat, wanneer)
- Time-travel debugging (state op elk moment)
- Tamper detection (hash chain verificatie)
- Event-driven architecture mogelijkheden

### Negative
- Complexere data model
- Hoger storage verbruik (alle events, niet alleen current state)
- State reconstructie kost tijd bij grote event logs
- Event schema migraties zijn complex (immutable events)

### Mitigations
- Snapshotting: Dagelijkse snapshots van state voor snelle reconstructie
- Event compaction: Oude events archiveren naar cold storage
- CQRS: Separate read models voor snelle queries
