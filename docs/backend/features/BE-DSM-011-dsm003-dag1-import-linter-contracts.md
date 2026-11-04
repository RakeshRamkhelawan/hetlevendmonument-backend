# BE-DSM-011: SP-DSM-003 Dag 1 -- Import-linter Contract 2+5 activeren

Sprint: SP-DSM-003 Dag 1
Datum: 2026-06-17
Status: APPROVED

---

## Wat is er gedaan

Contract 2 (`no-cross-router`) en Contract 5 (`governance-independence`) zijn geactiveerd
in `.importlinter`. Contract 3 (`layers`) is niet geactiveerd wegens stopvoorwaarde (>50
violations). 6 stale `ignore_imports` entries zijn verwijderd uit Contract 1.

---

## Contract 2 -- no-cross-router

### Probleem

De originele definitie gebruikte dezelfde wildcard `src.core.api.v1.*.router` in zowel
`source_modules` als `forbidden_modules`. Import-linter geeft bij zelf-referentie de fout
"Modules have shared descendants" en kan het contract niet evalueren.

### Oplossing

Optie B: 4 specifieke domeinpakketten (`agentic`, `als`, `cva`, `focus_builder`) mogen
`sync` niet importeren. De dekking is bewust smaller dan de originele invariant; de
ADR-034 grens wordt aanvullend bewaakt door AST-tests in
`tests/architecture/test_adr034_orchestration_boundary.py`.

```ini
[importlinter:contract:no-cross-router]
name = API-routers mogen niet direct elkaars domeindependencies importeren
type = forbidden
source_modules =
    src.core.api.v1.agentic
    src.core.api.v1.als
    src.core.api.v1.cva
    src.core.api.v1.focus_builder
forbidden_modules =
    src.core.api.v1.sync
allow_indirect_imports = false
unmatched_ignore_imports_alerting = warn
```

Verificatie: `lint-imports` geeft 0 violations voor dit contract.

---

## Contract 3 -- layers (NIET geactiveerd)

### Stopvoorwaarde getriggerd

Contract 3 tijdelijk uncommenteerd in `.importlinter-test3` en gemeten:
output >11511 tekens, duidelijk meer dan de 50-violations stopgrens. Root cause: de
domeinmodules op dezelfde laag (`copilot | als | workflow | agents | governance`)
importeren elkaar uitgebreid by design per ADR-027 en ADR-034. De `layers` constraint
vereist dat same-layer modules elkaar niet importeren, wat fundamenteel incompatibel is
met de huidige architectuur.

Backlog: SP-DSM-004 -- herontwerp `layers` contract met permissieve same-layer definitie.

---

## Contract 5 -- governance-independence

### Probleem

De originele definitie gebruikte `type = independence`, wat elke richting van koppeling
verbiedt. ADR-027 staat `copilot -> governance` (Council deliberation) bewust toe, waardoor
de definitie altijd zou falen.

### Oplossing

Herontwerp naar unidirectioneel forbidden: alleen de verkeerde richting (`governance ->
copilot`) is verboden. De toegestane richting (`copilot -> governance`) wordt niet geblokkeerd.

`allow_indirect_imports = true` zodat Contract 5 alleen directe imports bewaakt. Transitieve
paden via gedeelde infrastructure (bijv. via `src.workers`) worden niet individueel gevangen;
uitbreiding naar `false` in SP-DSM-004 zodra de 2 directe violations gefixed zijn.

2 directe violations gevonden in governance die copilot types importeren (verkeerde richting):
- `hash_chain.py` importeert `OfficerVerdict` uit `copilot.council.types`
- `retention_cleanup.py` importeert `CouncilDecisionRow`/`OfficerVerdictRow` uit `copilot.council.models`

Beide zijn `known-violation` met backlog SP-DSM-004. De fix: verplaats deze types naar
`src.core.governance.models` of een shared module.

```ini
[importlinter:contract:governance-independence]
name = Governance mag niet copilot importeren (ADR-027: copilot->governance is by design)
type = forbidden
source_modules =
    src.core.governance
forbidden_modules =
    src.core.copilot
# allow_indirect_imports=true: transitieve paden via gedeelde infrastructure worden niet
# individueel gevangen -- uitbreiding naar false in SP-DSM-004 zodra directe violations gefixed zijn.
allow_indirect_imports = true
unmatched_ignore_imports_alerting = warn
ignore_imports =
    # known-violation: governance.hash_chain importeert copilot council types -- backlog SP-DSM-004
    src.core.governance.hash_chain -> src.core.copilot.council.types
    # known-violation: governance.retention_cleanup importeert copilot council models -- backlog SP-DSM-004
    src.core.governance.retention_cleanup -> src.core.copilot.council.models
```

Verificatie: `lint-imports` geeft 0 violations voor dit contract.

---

## Stale ignore_imports verwijderd

6 entries voor `src.core.api.webhooks.dependencies` verwijderd uit Contract 1's
`ignore_imports`. Deze entries matchten nooit omdat geen enkel `source_module` van Contract 1
(alle `*.router` bestanden) `webhooks.dependencies` importeert. De entries kwamen uit twee
toevoegingsrondes (vroege fase en SP-DSM-002 Dag 5).

---

## Architectuurtest bijgewerkt

`tests/architecture/test_dsm_grade_a_plus.py:95` -- xfail-reden bijgewerkt van
`"Contract 2/3/5 disabled until SP-AGT-004 + SP-API-011"` naar
`"Contract 3 (layers) disabled -- SP-DSM-004"`. Contracts 2 en 5 zijn nu actief; alleen
Contract 3 blokkeert nog de groene test.

---

## Eindstaat .importlinter

| Contract | Status |
|----------|--------|
| 1 api-no-domain | Actief, 0 violations |
| 2 no-cross-router | Actief (nieuw), 0 violations |
| 3 layers | Uitgecommentarieerd (backlog SP-DSM-004) |
| 4 no-cross-gateway | Actief, 0 violations |
| 5 governance-independence | Actief (nieuw), 0 violations |
| 6 agent_runtime_boundary | Actief, 0 violations |
| 7 agent_runtime_no_db | Actief, 0 violations |

`lint-imports`: 6 kept, 0 broken, 0 warnings
`pyright`: 0 errors (baseline ongewijzigd)
`ruff`: 0 errors
`pytest tests/architecture/`: 12 passed, 4 xfailed (baseline ongewijzigd)


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: SP-DSM-003 Dag 1: Contract 2+5 geactiveerd. Contract 3 deferred (>50 violations, SP-DSM-004). 6 stale entries verwijderd. 6 kept, 0 broken. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker start of gebruikt SP-DSM-003 Dag 1: Contract 2+5 geactiveerd. Contract 3 deferred (>50 violations, SP-DSM-004). 6 stale entries verwijderd. 6 kept, 0 broken..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
