# Review BE-RTR-017 — Missions Domain Migration (SP-API-004 Dag 2)

## Uitslag: APPROVED WITH MINOR GAPS

| Categorie | Bevinding | Ernst | Status |
|-----------|-----------|-------|--------|
| Architectuur | drie-laags compositie correct (Laag 1/2/3) | INFO | OK |
| Tenant isolatie | get_tenant() via ContextVar, consistent met audit-domein | INFO | OK |
| Lege paden | "" vervangen door "/" in alle sub-routers | INFO | OK |
| orphan:exempt | op regel 1 van legacy shim aanwezig | INFO | OK |
| Registratie | core_api.py bijgewerkt, domain_router gebruikt | INFO | OK |
| Fitness gate | test_missions_flat_file_migrated_to_v1 GROEN | INFO | OK |
| MINOR: schemas.py bevat `User` import die alleen in type-hint gebruikt wordt | LOW | OPEN — acceptabel |
| MINOR: crud_router.py importeert HTTPException/datetime deferred (in functies) | LOW | OPEN — acceptabel, vermijdt circulaire imports |

## Checklist

- [x] Drie-laags structuur gevolgd (Laag 1/2/3, ADR-033)
- [x] Geen directe `src.core.database` imports in router-bestanden
- [x] tenant_id uit middleware ContextVar (nooit uit request body)
- [x] Alle 8 routes aanwezig in sub-routers
- [x] `# orphan:exempt` op regel 1 van legacy shim
- [x] Lege paden `""` vervangen door `"/"`
- [x] `datetime.now(timezone.utc)` (geen naive datetimes)
- [x] logger.error() met exc_info=True aanwezig in explainability
- [x] Trainingssamenvatting aanwezig in spec (3 flows)
- [x] Equivalentietest GROEN (137 tests PASS)

## Eindoordeel

APPROVED WITH MINOR GAPS — de twee MINOR gaps zijn geen blockers en worden
niet in deze sprint opgelost. De migratie is correct en consistent met
eerder gemigreerde domeinen (audit, security, agents).
