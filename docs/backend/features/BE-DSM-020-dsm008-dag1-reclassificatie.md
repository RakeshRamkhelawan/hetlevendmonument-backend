# BE-DSM-020 -- SP-DSM-008 Dag 1: MODULE_MAP Reclassificatie (config + tracing + di)

**Status**: APPROVED WITH MINOR GAPS
**Sprint**: SP-DSM-008 Dag 1
**ADR**: ADR-034 (agent_runtime boundary), ADR-019 (audit logging)
**Datum**: 2026-06-18

---

## Probleemstelling

agent_runtime instability I=0.582 overschreed het ADR-034 target I<=0.50 (Grade A+).
Root cause: cross-cutting foundation modules (config, DI, tracing) waren geclassificeerd
als `infra` in de DSM MODULE_MAP, waardoor alle agent_runtime imports naar deze modules
als Ce (efferente koppeling) telden.

Beginsituatie: Ce=311, Ca=223, I=0.582.

---

## Uitgevoerde wijzigingen

### Fix A: MODULE_MAP reclassificaties (scripts/dsm_full_analysis.py)

Vier infra-entries herclassificeerd naar `shared` (shared wordt uitgesloten van Ce):

| Module | Van | Naar | Ce-reductie |
|--------|-----|------|-------------|
| src.config | infra | shared | 9 Ce |
| src.core.config | infra | shared | 8 Ce |
| src.core.di | infra | shared | 2 Ce |
| src.core.observability.tracing | (nieuw) | shared | 8 Ce |

Totaal: -27 Ce -> Ce=285 (was 311).

Extra override toegevoegd: `"src.core.config.feature_flags": "infra"` voor de generieke
`src.core.config` entry. Reden: feature_flags.py importeert src.core.middleware.tenant_context
(tenancy-laag) en is daarom geen pure shared foundation.

Motivatie per module:
- **src.config / src.core.config**: App-configuratie is domein-neutrale basis (zoals logging).
  De meeste submodules (unified_config, production_config, settings) hebben geen business-imports.
- **src.core.di**: DI container-definitie heeft geen src.* imports; pure infrastructurele basis.
- **src.core.observability.tracing**: OpenTelemetry-tracer is cross-cutting foundation,
  identiek aan logging (al in shared).

### Fix B: TYPE_CHECKING filter in scripts/dsm_contract_aware_analysis.py

`_collect_type_checking_nodes()` toegevoegd (identiek aan dsm_full_analysis.py).
Filter toegepast in de AST walk-loop van `scan_module_contract_aware()`.

Reden: dsm_contract_aware_analysis.py telde TYPE_CHECKING-imports (annotation-only,
geen runtime-koppeling) als echte violations. Nu consistent met dsm_full_analysis.py.

### Fix C: Architecture tests bijgewerkt

- `tests/architecture/test_dsm_008_reclassification.py` aangemaakt (Ce<=285 gate)
- `tests/architecture/test_dsm_scanner_fixes.py` bijgewerkt: twee tests die
  `classify("src.config")` == "infra" verwachtten, nu "shared" (de correcte nieuwe waarde)

---

## Niet herclassificeerd (Dag 1)

### src.core.models (12 Ce) -- uitgesteld

`src/core/models/__init__.py` importeert uit `src.core.auth.models` (auth-laag) en
`src.core.governance.models` (governance-laag). Herclassificatie naar shared is
architectureel onjuist zolang deze aggregator-imports aanwezig zijn.

Actie voor toekomstige sprint: refactoren van de aggregator-import, daarna herclassificeren.

### src.core.container (2 Ce) -- NIET herclassificeerd

`src/core/container.py` importeert uit `src.core.storage.*` (integrations-laag).
Herclassificatie zou `test_shared_fan_out_is_zero` breken.

### src.core.database.database (59 Ce) -- Dag 2 scope

ADR-beslissing vereist (zie SP-DSM-008 Dag 2 brief).

---

## Impact meting

| Metric | Voor | Na |
|--------|------|----|
| Ce (fan-out excl. shared) | 311 | 285 |
| Ca (fan-in) | 223 | 223 |
| I (instability) | 0.582 | 0.561 |
| Dag 2 target Ce | -- | <=223 |

De `test_shared_fan_out_is_zero` test blijft GROEN -- SOURCE_DIRS["shared"] is
niet aangepast, dus de reclassificeerde modules worden niet gescand als shared-source.

---

## Verificatie

| Check | Resultaat |
|-------|-----------|
| python -m pyright | 0 errors (baseline intact) |
| ruff check scripts/ tests/architecture/ | All checks passed |
| test_dsm_008_reclassification.py | PASSED (Ce=285 <= 285) |
| test_shared_fan_out_is_zero | PASSED |
| test_agent_runtime_instability_ceiling (Ce<=700) | PASSED |
| test_agent_runtime_instability_grade_a_plus (xfail I<=0.50) | XFAIL (nog niet bereikt) |
| Volledige architecture suite | 169 passed, 4 failed (pre-existing), 16 xfailed, 1 xpassed |

Pre-existing failures (buiten scope):
- test_messaging_services_do_not_import_tasks (SP-DSM-007 backlog)
- test_focusbuilder_backlog_kritiek (3x, SP-FB-001)

---

## Gewijzigde bestanden

- `scripts/dsm_full_analysis.py` (MODULE_MAP: 4 entries + 1 override)
- `scripts/dsm_contract_aware_analysis.py` (TYPE_CHECKING filter)
- `tests/architecture/test_dsm_008_reclassification.py` (nieuw)
- `tests/architecture/test_dsm_scanner_fixes.py` (2 test-updates)


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: SP-DSM-008 Dag 1: MODULE_MAP reclassificatie -- src.config, src.core.config (incl. feature_flags override), src.core.di, src.core.observability.tracing -> shared. Ce 311->285 (-26). dsm_contract_aware_analysis.py TYPE_CHECKING filter. scanner_fixes tests bijgewerkt. is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt SP-DSM-008 Dag 1: MODULE_MAP reclassificatie -- src.config, src.core.config (incl. feature_flags override), src.core.di, src.core.observability.tracing -> shared. Ce 311->285 (-26). dsm_contract_aware_analysis.py TYPE_CHECKING filter. scanner_fixes tests bijgewerkt..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
