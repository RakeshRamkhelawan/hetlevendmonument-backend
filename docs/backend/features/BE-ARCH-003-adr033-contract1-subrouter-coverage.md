# BE-ARCH-003: ADR-033 Contract 1 sub-router-dekking + facade-fixes

**Sprint:** AUDIT-ARCH-2026-07-02 Dag 2 Groep 7
**Datum:** 2026-07-02
**Status:** APPROVED
**ADR:** ADR-033

## Probleem

`.importlinter` Contract 1 dekte alleen bestanden die letterlijk `router.py`
heten (`source_modules = src.core.api.v1.*.router`). De ~151 `*_router.py`
sub-routers (bijv. `board_router.py`, `gatekeeper_hitl_router.py`) vielen buiten
die dekking. 3 concrete facade-bypasses waren daardoor nooit gedetecteerd.

## Oplossing

- Empirisch bevestigd dat import-linter geen partiele-segment-wildcards
  ondersteunt (`src.core.api.v1.*.*_router` faalt met "A wildcard can only
  replace a whole module") -- Contract 1 zelf kan dus niet verbreed worden.
- Nieuwe AST-gebaseerde architecture-test
  (`tests/architecture/test_importlinter_contract1_covers_sub_routers.py`)
  handhaaft dezelfde regel (geen directe imports van Contract 1's
  forbidden_modules-lijst, `.dependencies`-imports toegestaan) op alle
  `*_router.py`-bestanden, inclusief correcte resolutie van relative imports.
- 3 concrete facade-bypasses gefixed via de bestaande `dependencies.py`-facades:
  `gatekeeper_hitl_router.py` (GatekeeperRepository), `board_router.py`
  (BoardService/BoardRoleError/BoardServiceError/GoldenRuleR3Violation, 4 nieuwe
  re-exports in `company/dependencies.py`), `agency_capabilities.py` (6 dode
  imports verwijderd, 2 echt-gebruikte via `agentic/dependencies.py`).

## Trainingssamenvatting

- Actor: developer die een nieuwe `*_router.py`-sub-router toevoegt of wijzigt
- Voorwaarde: bestand matcht `src/core/api/**/*_router.py`
- Actie: bestand importeert direct uit een forbidden-module (database,
  governance, learning, agents, workflow, llm, services, ml, als,
  semantic_router) i.p.v. via `*.dependencies`
- Systeemreactie: `pytest tests/architecture/test_importlinter_contract1_covers_
  sub_routers.py` faalt met de exacte bestand:module-combinatie
- Succesrespons: import via `*.dependencies` -- test blijft groen
- Foutrespons: CI faalt, PR kan niet gemerged worden zonder de facade-fix of een
  expliciete `KNOWN_VIOLATIONS`-allowlist-entry (met eigen falende
  regressietest die aangeeft dat de allowlist niet verouderd is)
- Uitzonderingen: relative imports (`from . import`) worden nu ook correct
  geresolved naar hun absolute module-pad (initiele versie miste dit -- gefixed
  na code-reviewer-bevinding)

## Test bewijs

```
pytest tests/architecture/test_importlinter_contract1_covers_sub_routers.py \
  tests/unit/test_board_api.py tests/unit/api/test_gatekeeper_router_equivalence.py \
  tests/unit/test_gatekeeper_router_integration.py tests/unit/api/v1/agentic/test_agents.py \
  tests/unit/agency/test_agency_capabilities_real.py tests/unit/test_sp_api_010_router_boundary.py -v
72 passed

lint-imports --config .importlinter -- 9 contracts kept, 0 broken (ongewijzigd t.o.v. baseline)
ruff check -- 0 errors, python -m pyright -- 0 errors (baseline)
```

## Reviewers

code-reviewer: GO -- geen circulaire-import-risico's gevonden, dode-import-
verwijdering geverifieerd veilig (grep over volledig bestand), glob-dekking
correct (151 bestanden gematcht, 3 BOM-bestanden correct afgehandeld). Non-
blocking suggestie (relative-import-resolutie) direct meegenomen.
security-reviewer: GO -- runtime-equivalentie bevestigd voor alle 3 facade-
redirects (zelfde object via facade als voorheen direct), exception-matching
blijft correct werken (class-identity, niet import-pad-afhankelijk).

## Backlog

Geen expliciete backlog-items voor Groep 7 zelf. Het risico van onbekende
extra violations bij een bredere toekomstige scan bleef beperkt tot de 3 al
bekende gevallen (geen scope-explosie opgetreden).
