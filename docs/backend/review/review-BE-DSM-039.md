# Review BE-DSM-039 -- SP-DSM-018 Dag 1: auth/api_deps.py facade + Batch A

## Status

APPROVED

## Reviewer

Self-review (Gate 2 dispensatie: facade = 31 regels, batch migratie = mechanische substitutie)

## Datum

2026-06-26

## Bevindingen

### Laag 1 -- Code (CLAUDE.md patronen)

- tenant_id: geen aanraking -- PASS
- datetime: geen aanraking -- PASS
- best_effort: geen aanraking -- PASS
- ASCII-only: ja -- PASS
- api_deps.py `require_tenant_id` NIET opgenomen (zit in middleware, niet auth) -- PASS

### Laag 2 -- Security

- Facade re-exporteert bestaande auth-primitives; geen nieuwe logica -- PASS
- Geen new attack surface (facade is pure re-export) -- PASS
- `rbac_decorator.require_permission` NIET per abuis opgenomen (is andere functie dan `dependencies.require_permission`) -- PASS

### Laag 3 -- Tests

- 2 arch tests GROEN: facade_exists + Ce<=400 -- PASS
- DSM scan bevestigt core_api->auth 450->375 (-75 edges) -- PASS
- Pyright 0 errors na migratie -- PASS

### Laag 4 -- Documentatie

- Feature spec aangemaakt: docs/backend/features/BE-DSM-039-* -- PASS
- ID-REGISTRY update: aanwezig in commit b3806b41 -- PASS

### Laag 5 -- Architectuur

- ADR-033: migratie raakt NIET router.py laag 1 architectuur -- PASS
- ADR-034: geen nieuwe laag-grenzen geschonden -- PASS
- Facade volgt zelfde patroon als runtime_deps.py (BE-DSM-038) -- PASS

### Gate 2 dispensatie argumentatie

- api_deps.py: 65 regels (pure re-exports, geen logica)
- 30 bestanden: elk 3-5 regels vervangen door 1 regel (mechanisch, geen logica)
- Geen nieuwe algoritmen, geen nieuwe dependencies
- Risico: import-fout bij verkeerd symbool -> direct zichtbaar via pyright (0 errors bevestigd)

Dispensatie geldig conform quality-gates.md: <50 regels nieuwe logica in productie.

## Eindoordeel

**APPROVED**

Geen blockers, geen CRITICAL/HIGH bevindingen. Migratie is puur mechanisch.
Pyright 0 errors + arch tests GROEN = Gate 3 voldaan.
