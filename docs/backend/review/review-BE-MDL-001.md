# Review: BE-MDL-001 PackFeedback + GlobalPack ORM Models

## Reviewer
Automated code-reviewer + quality-reviewer subagents (Laag A)

## Datum
2026-05-28

## Bevindingen

### Iteratie 1 (v1) — NEEDS REVISION

| Ernst | Bevinding | Status |
|-------|-----------|--------|
| CRITICAL | JSONB import ontbrak in models.py | Opgelost in v2 |
| HIGH | `PackFeedback.user_id` type hint `Mapped[int]` met `nullable=True` | Opgelost in v2 (`Mapped[int \| None]`) |
| HIGH | Ontbrekende CHECK constraint op `rating` (1-5) | Opgelost in v2 |
| MEDIUM | `GlobalPack.pack_data` type precisie `Mapped[dict]` | Opgelost in v2 (`Mapped[dict[str, Any]]`) |
| MEDIUM | `GlobalPack` mist `updated_at` | Opgelost in v2 |

### Iteratie 2 (v2) — APPROVED

- Alle CRITICAL/HIGH bevindingen opgelost.
- ADR-005 naleving geverifieerd: tenant_id NOT NULL + RLS.
- `clock_timestamp()` correct gebruikt per CLAUDE.md §11.5.
- Downgrade volledig: DROP POLICY → DROP INDEX → DROP TABLE.
- Type hints correct: `int | None`, `dict[str, Any]`, `datetime | None`.

### Overgebleven aantekeningen (LOW — geen blockers)

1. `tenant_isolation_policy` naam hergebruikt over tabellen — PostgreSQL-technisch correct (tabel-scoped).
2. `GlobalPack` heeft geen `index=True` op `name` — monitor query performance in dag 2 endpoints.
3. Semantiek `global_packs` + `tenant_id NOT NULL` is verwarrend — gedocumenteerd in model docstring.

## Verdict

**APPROVED WITH MINOR GAPS**

Minor gaps zijn preventief van aard en blokkeren dag-2 implementatie niet.
