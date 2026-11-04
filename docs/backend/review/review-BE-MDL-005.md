# Review BE-MDL-005 — ToolVersion ORM Model

**Datum:** 2026-05-28  
**Sprint:** SP-B02  
**Reviewer:** Laag A code-reviewer + Laag C security-reviewer (subagents)

---

## Verdict: APPROVED

---

## Checklist

| Check | Status | Opmerking |
|-------|--------|-----------|
| `tenant_id NOT NULL` | PASS | `nullable=False, index=True` |
| `tenant_id` eigen kolom (geen join nodig) | PASS | Directe filter mogelijk in queries |
| `tool_id` FK met `ondelete="CASCADE"` | PASS | `ForeignKey("tools.id", ondelete="CASCADE")` |
| `snapshot` is JSONB NOT NULL | PASS | `mapped_column(JSONB, nullable=False)` |
| `created_at` gebruikt `clock_timestamp()` | PASS | `server_default=func.clock_timestamp()` |
| Snapshot vastgelegd vóór version bump | PASS | `old_version = tool.version` vóór `tool.version += 1` |

---

## Bevindingen

Geen CRITICAL of HIGH bevindingen. Immutable-by-design: geen `updated_at` kolom — versie-rijen worden nooit gewijzigd.
