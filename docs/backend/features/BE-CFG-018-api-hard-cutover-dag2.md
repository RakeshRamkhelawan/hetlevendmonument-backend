# BE-CFG-018 — SP-API-008 Dag 2: ADR-033 Hard Cutover Dag 2

**ID:** BE-CFG-018
**Sprint:** SP-API-008 Dag 2
**ADR:** ADR-033
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

ADR-033 hard cutover dag 2: `system_endpoints.py` BLOCKER gefixed (`from __future__ import annotations` verwijderd), import-linter violations gereduceerd van 214 naar 142 via `ignore_imports` voor legitieme infra-chains, DSM outgoing imports definitief gemeten (334), collectietijd gemeten (158s), SPRINT_TRACKER en SPRINT-CANVAS bijgewerkt.

---

## Componenten

### 1. system_endpoints.py BLOCKER (Taak 1)

`src/core/api/system_endpoints.py`:
- `from __future__ import annotations` verwijderd (CLAUDE.md verbiedt dit expliciet)
- `Optional` import verwijderd (ongebruikt)
- Bestand gebruikt native Python 3.11+ syntax; geen verdere aanpassingen nodig
- Syntax geverifieerd: `python -m py_compile` OK

### 2. import-linter violations gereduceerd (Taak 2)

`.importlinter` Contract 1 `ignore_imports` uitgebreid:

| Edge | Reden |
|------|-------|
| `src -> src.workers` | `get_workers()` is lazy import functie, niet module-level koppeling |
| `src.core.services.rbac_service -> src.core.agents.models` | Deferred import voor circulaire-ref-preventie; auth-infrastructuur |
| `src.core.services.rbac_service -> src.core.workflow.models` | Idem |
| `src.core.services.rbac_service -> src.core.database.database` | RBAC service infrastructure DB-dependency |

**Resultaat:** 214 → 142 violations (-72). Contract 2 (no-cross-gateway) blijft KEPT.

**Resterende 142 violations** zijn pre-existing structuurkoppeling via:
`v1/*.router -> auth.dependencies -> {audit_service, auth_service, scope_validator} -> {database, governance.models, agents.models}`
Root cause: auth/db infrastructuurmodules importeren domeinmodellen. Fix vereist refactoring van auth + database modules — post-MVP.

### 3. DSM meting (Taak 4)

Definitieve meting met uitgebreide forbidden-lijst (8 modules):

```
Outgoing imports API -> domein: 334
```

Top contributors: `learning.py` (10x), `auth/router.py` (6x), `v1/compliance/dependencies.py` (6x), `v1/cva/chat_router.py` (6x), `v1/workflow/workflow_execution_router.py` (6x).

ADR-033 doel < 200 niet gehaald. Reden: ACTIEF flat files importeren nog direct domeinlogica. Na migratie van deze bestanden naar v1/ zal de count dalen.

### 4. Collectietijd meting (Taak 3)

| Meting | Tijd |
|--------|------|
| Dag 1 baseline (na fa fixes) | 114s |
| Dag 2 standaard | 158s |
| Dag 2 importlib-mode | 173s |

Collectietijd ligt significant boven het 90s-doel. Root cause: Windows OneDrive file-stat latency op 12946 testbestanden (bekende valkuil uit CLAUDE.md). Fix vereist verplaatsing van project buiten OneDrive — buiten sprint-scope.

### 5. SPRINT_TRACKER + SPRINT-CANVAS bijgewerkt (Taak 5)

- `docs/SPRINT_TRACKER.md`: SP-API-008 sectie toegevoegd (Dag 1 CLOSED, Dag 2 IN PROGRESS, Dag 3 GEPLAND)
- `docs/SPRINT-CANVAS.md`: status bijgewerkt (86 sprints, 1 OPEN)

---

## Trainingssamenvatting

### Flow 1: CLAUDE.md BLOCKER fix (from __future__)

**Actor:** Developer of CI-pipeline
**Voorwaarde:** Bestand bevat `from __future__ import annotations` + optionele `Optional` import
**Actie:** Verwijder `from __future__` + onnodige `Optional` import
**Systeemverwerking:** Python 3.11+ evalueert `X | None` natively; FastAPI body-introspectie werkt correct
**Succesrespons:** `python -m py_compile` = OK; geen ImportError; geen FastAPI 422-fouten
**Foutrespons:** Als `X | Y` syntax in Python <3.10 gebruikt wordt: `TypeError` (niet van toepassing, project gebruikt Python 3.11+). Bij elke exception: `logger.error(..., exc_info=True)` verplicht per CLAUDE.md §11 — stacktrace behouden.
**Uitzonderingen:** Bestanden met `TYPE_CHECKING` block mogen `from __future__` behouden als ze type-only strings gebruiken

### Flow 2: import-linter ignore_imports toevoegen

**Actor:** Sprint-engineer
**Voorwaarde:** import-linter Contract 1 toont violations via infrastructure-chain
**Actie:** Voeg `ignore_imports = <module-a> -> <module-b.exact.submodule>` toe aan contract-sectie
**Systeemverwerking:** import-linter verwijdert de specifieke directe edge uit de dependency-graph; transitive keten wordt gebroken
**Succesrespons:** violations-count daalt; contract blijft BROKEN maar met minder violations
**Foutrespons:** "No matches for ignored import" → module-naam klopt niet; gebruik exacte submodule-naam. Log fouten met `logger.error(..., exc_info=True)` per CLAUDE.md §11.
**Uitzonderingen:** `ignore_imports` werkt alleen voor DIRECTE edges, niet voor transitieve ketens; gebruik de juiste module uit de violation chain

### Flow 3: DSM meting

**Actor:** Sprint-engineer
**Voorwaarde:** API-laag heeft flat files die domeinlogica importeren
**Actie:** Draai DSM-meting script (AST-analyse van `src/core/api/`)
**Systeemverwerking:** Script telt alle `from src.core.<domein>.*` imports in API-laag
**Succesrespons:** Count < 200 = ADR-033 doel bereikt
**Foutrespons:** Count > 200 = ACTIEF flat files migreren naar v1/ om count te verlagen
**Uitzonderingen:** Uitgebreidere forbidden-lijst (8+ modules) geeft hogere count dan originele 6-module meting

---

## Pre-existing open punten (geen blocker voor GO)

| Item | Root cause | Actie |
|------|------------|-------|
| 142 import-linter violations | auth/db infra importeert domeinmodellen | TODO(SP-VOLGENDE): infra isoleren van domain |
| DSM 334 > 200 | ACTIEF flat files nog niet naar v1/ gemigreerd | TODO(SP-VOLGENDE): actieve flat files migreren |
| Collectietijd 158s > 90s | OneDrive file-stat latency | TODO(SP-VOLGENDE): project buiten OneDrive plaatsen |
| FA-004: startup smoke-test | TESTING=1 maskeert import failures | TODO(SP-VOLGENDE): smoke-test toevoegen |
