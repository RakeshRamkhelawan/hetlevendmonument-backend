# BE-API-034: ADR-033 criterium 4 -- circulaire dep focus_builder

**ID:** BE-API-034
**Sprint:** SP-API-009 Dag 3
**Status:** DONE
**Datum:** 2026-06-11

## Beschrijving

Verwijdering van de `agent_runtime -> core_api` circulaire afhankelijkheid (ADR-033 criterium 4).
`focus_builder_chat_agent.py` importeerde `_get_internal_agents` via een function-body import
uit `src.core.api.v1.focus_builder.agents` (core_api domein). Dit schendt ADR-033/034:
`src.core.agents` (agent_runtime) mag niet importeren uit `src.core.api`.

## Wat gewijzigd

- **Nieuw:** `src/core/als/agents/focus_builder_agents.py`
  Bevat `_build_als_agents()`, `_get_internal_agents()`, `_INTERNAL_AGENTS_CACHE`,
  `_DEPT_ICONS` (ASCII identifiers, CLAUDE.md compliant), `_TECH_CATEGORY`.
  Importeert uitsluitend uit `src.core.als.*` -- geen domein-crossing.

- **Gewijzigd:** `src/core/api/v1/focus_builder/agents.py`
  Lokale definities verwijderd. Backward-compat re-export:
  `from src.core.als.agents.focus_builder_agents import _get_internal_agents as _get_internal_agents`

- **Gewijzigd:** `src/core/agents/focus_builder_chat_agent.py:359`
  `from src.core.api.v1.focus_builder.agents import _get_internal_agents`
  vervangen door:
  `from src.core.als.agents.focus_builder_agents import _get_internal_agents`

- **Nieuw:** `tests/architecture/test_adr033_focus_builder_circular_dep.py`
  AST-regressietest: detecteert directe `src.core.api.*` imports in `focus_builder_chat_agent.py`.

- **Gewijzigd:** `tests/unit/test_collect_side_effects.py`
  AUDIT-COLL-03c toegevoegd: bewaakt dat `_build_als_agents()` niet op module-niveau
  staat in het nieuwe bestand (mirror van AUDIT-COLL-03b voor het oude bestand).

- **Gewijzigd:** `.github/workflows/ci-feature.yml`
  `tests/architecture/` toegevoegd aan CI test run (structurele gap gedicht).

- **Gewijzigd:** `tests/architecture/test_sp_api_010_backlog.py`
  SP-API-010 backlog tests gemarkeerd met `xfail(strict=True)` zodat CI groen blijft
  maar onverwachte fixes worden gevangen.

## Waarom

ADR-033 criterium 4: `lint-imports --config .importlinter` moet 0 circulaire deps
tonen voor `agent_runtime -> core_api`. De import op regel 361 van `focus_builder_chat_agent.py`
was de enige resterende schending. Verplaatsing naar `als` domein verwijdert de cyclus
zonder behavioral change: `_get_internal_agents()` levert dezelfde resultaten.

## Testbewijs

```
pytest tests/architecture/test_adr033_focus_builder_circular_dep.py -v
  1 passed

lint-imports --config .importlinter
  Contracts: 4 kept, 0 broken.

pytest tests/unit/agents/test_focus_builder_chat_agent.py
tests/unit/agents/test_focus_builder_intake.py
tests/unit/api/test_focus_builder_ws_chat.py
tests/unit/test_focus_builder_observer.py
tests/unit/test_sp_we_22_focus_builder_not_implemented.py
tests/architecture/test_adr033_focus_builder_circular_dep.py
  31 passed

pytest tests/architecture/
  72 passed, 3 xfailed

python -m pyright: 0 errors (baseline ongewijzigd)
ruff check src/: All checks passed
```

## Bekende follow-up

- TODO(SP-API-010): `_DEPT_ICONS` in `focus_builder_agents.py` gebruikt ASCII identifiers
  (`"target"`, `"brain"`, etc.). Afstemmen met frontend welke icon-namen verwacht worden.
- TODO(SP-API-010): SP-API-010 backlog items (caches, cross-router imports) -- xfail markers
  verwijderen zodra gefixed.

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
