# Review: BE-MDL-007 EU AI Act Compliance ORM Models

## Reviewer
Automated code-reviewer + doc-reviewer subagents (Laag A), 2 review iteraties

## Datum
2026-05-29

## Bevindingen

### Iteratie 1 (v1) — NEEDS REVISION

| Ernst | Bevinding | Status |
|-------|-----------|--------|
| CRITICAL | Foutrespons Flow 1 incorrect: HTTP 422 vs 400 bij service-laag ValueError | Opgelost in v2 |
| CRITICAL | Succesrespons Flow 1: `status = "reported"` zonder mapping naar DB kolom `resolution_status` | Opgelost in v2 |
| CRITICAL | Flow 2 Succesrespons: `log_provenance()` retourneert `ModelProvenanceDB`, niet `record_id string` | Opgelost in v2 |
| HIGH | Index naam discrepantie: `ix_incident_tenant_id` ORM vs migratie gebruiken verschillende mechanismen | Opgelost in v2 (note toegevoegd) |
| HIGH | ModelProvenanceDB scope incorrect: alleen Article 53 genoemd, ook Article 12 (transparency) | Opgelost in v2 |
| HIGH | ID-REGISTRY niet bijgewerkt na spec aanmaken | Opgelost in finale stap |
| HIGH | Flow 3 Foutrespons: "lege lijst" was succespad, niet foutpad | Opgelost in v2 |
| MEDIUM | Flow 2 systeemverwerking: aanroepsignature `log_provenance()` onjuist beschreven | Opgelost in v2 |
| MEDIUM | Geen acceptatiecriteria sectie | Opgelost in v2 |
| MEDIUM | Geen retentie-waarschuwing voor nullable `retention_until` (silent compliance gap) | Opgelost in v2 |

### Iteratie 2 (v2) — APPROVED

- Alle CRITICAL en HIGH bevindingen opgelost.
- ADR-005 naleving geverifieerd: `tenant_id NOT NULL` + RLS op beide tabellen.
- `clock_timestamp()` correct gebruikt per CLAUDE.md §11.5.
- `ondelete="RESTRICT"` op beide tenant FKs bevestigd (NOOIT CASCADE).
- Downgrade volledig: DROP POLICY -> DROP INDEX -> DROP TABLE voor beide migraties.
- Article 12 + Article 53 scope correct gedocumenteerd voor `ModelProvenanceDB`.
- Retention-waarschuwing toegevoegd voor `retention_until` nullable valkuil.
- Acceptatiecriteria sectie aanwezig met 5 testbare criteria.

### Overgebleven aantekeningen (LOW -- geen blockers)

1. Index naam discrepantie ORM vs migratie gedocumenteerd (note aanwezig in spec).
2. `get_expired_records()` DB-fout nu correct gedocumenteerd als SQLAlchemy exception.
3. Beide migratie offline dry-runs slagen (`alembic upgrade head --sql`).

## Verdict

**APPROVED WITH MINOR GAPS**

Alle CRITICAL en HIGH bevindingen opgelost. Minor gaps zijn documentatief van aard
en blokkeren implementatie niet.
