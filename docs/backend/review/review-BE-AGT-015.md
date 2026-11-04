# Review BE-AGT-015: CritiqueStore -> PostgreSQL Persistentie

**Sprint:** SP-AGT-005 Dag 1
**Datum:** 2026-06-19
**Reviewer:** code-reviewer + quality-reviewer (Laag A, Gate 2)
**Status:** APPROVED

---

## APPROVED -- geen blockers

Alle 4 unit tests GROEN. pyright 0 errors. ruff clean. Import-linter Cat B goedgekeurd.

---

## Bevindingen

### PASS: tenant_id patroon
`CritiqueRecord` ontvangt `tenant_id` uit het `Critique` dataclass object, dat geconstrueerd wordt
door `CriticMixin` op basis van agent-niveau context (niet uit request body). ADR-003 compliant.

### PASS: Lock-buiten patroon correct
In-memory operaties onder `async with self._lock:`. DB-write na lock release. Juist patroon.

### PASS: Best-effort DB write
`store()` catch-all wrapping + `_persist_to_db()` interne try/except. Twee lagen bescherming.

### PASS: Retention actor
`cleanup_agent_critiques` volgt bestaand patroon van `cleanup_council_decisions`.
`asyncio.run()` sync wrapper correct. `TenantFilterBypass()` aanwezig voor cross-tenant.

### PASS: Alembic migratie
Idempotent guard `if "agent_critiques" not in existing:`. RLS policy aanwezig.
`alembic heads` = 1. downgrade verwijdert policy VOOR tabel (juiste volgorde).

### PASS: Import-linter
Cat B entry in `[importlinter:contract:agent_runtime_no_db]` met beschrijvende comment.

### MINOR (backlog): CriticMixin fallback `getattr(self, "tenant_id", 1)`
Pre-existing: `CriticMixin` gebruikt `tenant_id=1` als fallback als het agent-attribuut ontbreekt.
Niet geintroduceerd door SP-AGT-005. Backlog item voor SP-AGT-005 Dag 2+.

### MINOR (backlog): `score` niet geclampd bij in-memory storage
`_persist_to_db()` clampt score via `max(0.0, min(1.0, ...))`. In-memory wordt niet geclampd.
Pre-existing inconsistentie. Geen actieve impact op productie. Backlog.

---

## Verdict

**APPROVED** -- 0 CRITICAL, 0 HIGH, 2 MINOR (pre-existing, backlog).
