# Backend Feature Specification

## Metadata

- Feature ID: BE-OPS-portal-ci (werk-ID; ID-REGISTRY wordt centraal door de regisseur bijgewerkt)
- Feature naam: Portal CI-job (portal/ gedekt door ci-feature.yml en de lokale act-runner)
- Status: Gebouwd, lokaal geverifieerd; review door aparte reviewer (buiten deze spec)
- Auteur: Iteratie-agent E1 (worktree `hlm-wk1-ci-portal`, branch `iter/wk1-ci-portal`)
- Reviewer: aparte reviewer (niet in deze iteratie)
- Datum: 2026-09-24
- Gerelateerde user story / ticket: markt-blokker "portal zit niet in de CI"
- Gerelateerde router / module: n.v.t. (CI/ops, geen applicatiecode)
- Gerelateerde frontend endpoints: n.v.t.
- Gerelateerde database tabellen: n.v.t.
- Versie: 1.0

---

## Doel en scope

### Doel

De frontend-map `portal/` (Vite/React/TypeScript, app `levend-monument-portal`) had
86 groene vitest-tests maar zat niet in de CI-beschrijving: `.github/workflows/ci-feature.yml`
had geen job voor `portal/`, en `scripts/run_ci_act.ps1` (de lokale act-runner, sinds
2026-09-14 de enige uitvoerder van CI) kende die map dus ook niet. Ongesteste
portal-wijzigingen konden ongezien naar `develop`. Deze feature voegt die dekking toe.

### In scope

- Nieuwe job `portal` in `.github/workflows/ci-feature.yml`: checkout, Node-setup met
  npm-cache op `portal/package-lock.json`, `npm ci`, `npm run type-check`, `npm test`
  (vitest), `npm run build`.
- Dezelfde job bekend maken bij de lokale runner `scripts/run_ci_act.ps1`:
  `ValidateSet` uitgebreid met `'portal'`, `'portal'` toegevoegd aan de standaard-batch
  (`$defaultTargets`), documentatie-commentaar bijgewerkt.
- Dekking door de bestaande guard
  `tests/architecture/test_local_ci_runner_covers_every_ci_job.py`, inclusief
  rood-bewijs (de guard faalde op `['portal']` toen de job in de workflow stond maar
  nog niet in de runner).

### Out of scope

- De bestaande `frontend`-job of andere jobs wijzigen.
- `ID-REGISTRY.md` (wordt centraal door de regisseur bijgevoegd).
- Review-document (aparte reviewer).
- De lint-toolchain van `portal/` herstellen (zie "Open aannames / bevindingen").
- `act` zelf draaien voor de nieuwe job (Docker-run); zie "Open aannames".

---

## Build summary

- Nieuw gebouwd: job `portal` in `ci-feature.yml`; spec; bevindingen-brief over de lint-stub.
- Gewijzigd: `scripts/run_ci_act.ps1` (ValidateSet, `$defaultTargets`, commentaarblok).
- Verwijderd: niets.
- Beinvloede bestaande flows: de standaard-batch van `run_ci_act.ps1` draait nu vijf
  jobs in plaats van vier (`bicep`, `security`, `docker-validate`, `frontend`, `portal`).

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-OPS-portal-ci | Portal CI-job | CI-workflow job | `.github/workflows/ci-feature.yml` (`jobs.portal`) | Nieuw | Lokale CI via act |
| BE-OPS-portal-ci-runner | Runner-dekking portal | PowerShell-script | `scripts/run_ci_act.ps1` | Wijziging | Lokale CI via act |
| BE-OPS-portal-ci-guard | Guard-dekking | Architecture-test | `tests/architecture/test_local_ci_runner_covers_every_ci_job.py` | Ongewijzigd (generiek, dekt automatisch) | Guard |

---

## Detaildocumentatie per artefact

## [BE-OPS-portal-ci] Portal CI-job

### 1. Type

- CI-workflow job (GitHub Actions YAML; uitvoering via `act` in Docker, sinds
  2026-09-14 draait GitHub Actions niet meer).

### 2. Locatie

- Bestandspad: `.github/workflows/ci-feature.yml`, sleutel `jobs.portal`, direct na de
  `frontend`-job.
- Runner-aankoppeling: `scripts/run_ci_act.ps1` (`ValidateSet`, `$defaultTargets`).

### 3. Gerelateerde flow

- Lokale CI: `.\scripts\run_ci_act.ps1` (standaard-batch) of `-Job portal` voor een losse run.

### 4. Doel

- Elke portal-wijziging die `develop` raakt is vooraf getoetst op typefouten,
  testfouten en buildfouten -- dezelfde bescherming die `frontend/` al had.

### 5. Functionele beschrijving

- De job installeert de portal-dependencies exact volgens `portal/package-lock.json`
  (`npm ci`), draait de TypeScript-compiler zonder emit (`tsc --noEmit`), draait de
  volledige vitest-suite (`vitest run`) en bouwt de productiebundle
  (`tsc && vite build`). Elke stap is blokkerend: een rode stap betekent een rode job.

### 6. Technische beschrijving

- Stappen gespiegeld aan de werkelijke scripts in `portal/package.json`
  (gelezen 2026-09-24):
  - `type-check`: `tsc --noEmit`
  - `test`: `vitest run`
  - `build`: `tsc && vite build`
  - `lint`: `eslint .` -- NIET opgenomen, zie sectie 11 (Business rules).
- `actions/setup-node@v4` met `node-version: ${{ env.NODE_VERSION }}` (20) en
  `cache: npm` met `cache-dependency-path: portal/package-lock.json` -- hetzelfde
  patroon als de `frontend`-job, dus aantoonbaar werkend onder `act` met het
  medium-image uit `.actrc`.
- Geen `fetch-depth: 0`: de portal-job heeft geen diff-gebaseerde gate (zoals de
  any-ratel in de frontend-job) en dus geen git-historie nodig.
- `timeout-minutes: 30`; lokaal gemeten duurt de duurste stap (vitest) ~76s en de
  build ~16s (2026-09-24, zie Acceptatiecriteria), dus 30 minuten is ruim.

### 7. Zichtbaarheids- en toegangsregels

- n.v.t. (geen runtime-API; de workflow staat op `workflow_dispatch`).

### 8-10. Request/response/validaties

- n.v.t. (geen endpoint).

### 11. Business rules

- **Geen lint-stap in deze job.** `portal/package.json` heeft wel een script
  `"lint": "eslint ."`, maar dat is een dode stub: eslint staat niet in
  `dependencies`/`devDependencies` en er is geen eslint-config nergens in `portal/`.
  Gemeten 2026-09-24 na `npm ci`:
  - `ls node_modules/.bin | grep -i eslint` -> geen treffer;
  - geen `.eslintrc*`/`eslint.config.*` in `portal/`;
  - `npm run lint` faalt met `'eslint' is not recognized as an internal or external
    command`.
  Een lint-stap opnemen zou de job per constructie altijd rood maken -- een job die
  altijd faalt went en maskeert echte failures (dezelfde reden als het stilleggen van
  de workflows zelf, zie de kop van `ci-feature.yml`). Herstel van de lint-toolchain
  (eslint + plugins + config + groen maken van de bestaande codebase) is een eigen
  bevinding met een eigen brief:
  `docs/agent-briefs/generated/2026-09-24-bevinding-portal-lint-stub.md`.
- De guard `test_local_ci_runner_covers_every_ci_job.py` eist dat de `ValidateSet`
  van de runner exact gelijk is aan de jobs in de workflow; beide testen in dat
  bestand moeten groen zijn.

### 12. Afhankelijkheden

- `portal/package-lock.json` (aanwezig; `npm ci` en de npm-cache hangen eraan).
- Node 20 (`env.NODE_VERSION`); portal gebruikt vite 5 / typescript 5.5, compatibel.
- `act` + Docker voor lokale uitvoering (`.actrc`: `catthehacker/ubuntu:act-latest`).
- De gedeelde venv voor de guard-test: `../het-levend-monument/.venv/Scripts/python.exe`.

### 13. Foutafhandeling

- Rode `npm ci`: lockfile drift of netwerkfout -- job faalt, geen verdere stappen.
- Rode `type-check`: TypeScript-fouten in `portal/src` -- blokkerend.
- Rode `test`: falende vitest-test -- blokkerend.
- Rode `build`: compile- of bundelfout -- blokkerend.
- Guard-test rood: workflow en runner zijn uit elkaar gelopen -- blokkerend in de
  testpoort (tests/architecture draait blokkerend in CI sinds 2026-07-31).

### 14. Transacties en data-integriteit

- n.v.t.

### 15. Telemetry / logging / tracing

- Job- en stapnamen zijn het log (`Portal`, `Install dependencies`, `Type check`,
  `Unit tests`, `Build check`). De runner rapporteert per job GROEN/ROOD en een
  eindresultaat.

### 16. Caching

- npm-cache via `actions/setup-node@v4` op `portal/package-lock.json`.

### 17. Acceptatiecriteria

Alle gemeten op 2026-09-24 in worktree `hlm-wk1-ci-portal` (Node v24.15.0, npm 11.12.1):

- [x] Guard ROOD zonder runner-wijziging: `1 failed, 1 passed`, faalende assertie noemt
  exact `['portal']` (mutatiebewijs dat de guard de nieuwe job dekt).
- [x] Guard GROEN na runner-wijziging: `2 passed in 0.62s`.
- [x] `npm ci` in `portal/`: exit 0 (alleen audit-adviezen, niet blokkerend).
- [x] `npm run type-check`: exit 0, geen output-regels met fouten (`tsc --noEmit`).
- [x] `npm test`: `Test Files 19 passed (19)`, `Tests 86 passed (86)`, exit 0,
  duur 75.52s. (jsdom-waarschuwingen "Not implemented: Window's getComputedStyle()
  with pseudo-elements" zijn bestaand gedrag van de suite, geen failures.)
- [x] `npm run build`: exit 0, `built in 16.09s`. Vite-waarschuwing over chunks > 500 kB
  (o.a. `vendor-maplibre` 1046 kB) is een waarschuwing, geen fout; niet blokkerend.
- [x] `npm run lint` is bewust NIET onderdeel van de job (zie sectie 11).
- [ ] `act`-run van de job zelf: niet gedraaid in deze iteratie (zie Open aannames).

### 18. Integratoruitleg

- Draai lokaal de volledige CI met `.\scripts\run_ci_act.ps1`; de portal-checks zitten
  daar nu automatisch bij.
- Draai alleen de portal-job met `.\scripts\run_ci_act.ps1 -Job portal`.
- De snelle variant zonder Docker: in `portal/` achtereen `npm ci`,
  `npm run type-check`, `npm test`, `npm run build` -- exact dezelfde commando's als
  de job.

### 19. Trainingssamenvatting

- Actor: developer die portal-code wijzigt.
- Voorwaarde: worktree op een iter-branch; Docker actief voor de act-variant.
- Actie (request): `.\scripts\run_ci_act.ps1` of `-Job portal`.
- Systeemverwerking: act start een container per job en voert de vijf stappen uit.
- Succesrespons: `>>> [act] GROEN: portal` en eindregel "alle gedraaide jobs 100% GROEN".
- Foutrespons: `>>> [act] ROOD: portal (exitcode N)` plus eindstatus NIET groen, exit 1.
- Uitzonderingen: lint is bewust afwezig (dode stub); zie bevindingen-brief.

---

## Pre-push hook en worktree-hooks (taak 6 verificatie)

Geverifieerd 2026-09-24, alleen-lezen in de hoofdmap:

- `git rev-parse --git-common-dir` vanuit de worktree `hlm-wk1-ci-portal` geeft
  `C:/Users/rsram/OneDrive/Documenten/GitHub/het-levend-monument/.git`.
- `ls C:/Users/rsram/OneDrive/Documenten/GitHub/het-levend-monument/.git/hooks/pre-push`
  toont dat de hook bestaat.
- Conclusie: de worktree deelt `.git/hooks` met de hoofdmap (worktrees hebben een eigen
  gitdir-bestand maar een gedeelde common-dir), dus de geinstalleerde pre-push hook
  geldt ook voor commits/pushes vanuit deze worktree. Er hoeft niets per worktree
  geinstalleerd te worden.

---

## Open aannames

- **De `act`-run van de portal-job is in deze iteratie niet gedraaid.** De stappen zijn
  individueel native groen bewezen (zie Acceptatiecriteria) en het gebruikte patroon
  (`setup-node@v4` + `cache: npm` + `working-directory`) is identiek aan de
  `frontend`-job die onder act gemeten groen is (CLAUDE.md-tabel, 2026-09-14). Risico:
  omgevingsverschillen (Node 20 in de container t.o.v. Node 24 lokaal) kunnen een
  afwijkende uitkomst geven. Verifieer met: `.\scripts\run_ci_act.ps1 -Job portal`.
- **Lockfile-drift tussen Node 20 en 24:** `npm ci` installeert exact de lockfile;
  er is geen `engines`-veld in `portal/package.json`, dus Node 20 wordt niet geweigerd.

## Open vragen

- Moet de portal-job ook een coverage-drempel krijgen zoals `frontend/`? Nu niet:
  `portal/package.json` heeft geen `test:coverage`-script. Eigen beslissing, niet in
  deze iteratie.

## Risico's

- De vitest-suite duurt lokaal ~76s; in een act-container met Node 20 kan dat langer
  zijn, maar ruim binnen `timeout-minutes: 30`.
- De dode lint-stub kan een volgende developer misleiden (`npm run lint` bestaat maar
  werkt niet). Gemitigeerd via de bevindingen-brief.

---

## Definition of Done

- [x] Feature is gebouwd (workflow-job + runner-dekking)
- [x] Guard-test dekt de nieuwe job (rood-bewijs + groen-bewijs)
- [x] Alle job-commando's lokaal groen bewezen
- [x] Open aannames benoemd
- [x] Bevinding (lint-stub) heeft een eigen brief in `docs/agent-briefs/generated/`
- [ ] Review door aparte reviewer (buiten deze iteratie)
- [ ] ID-REGISTRY bijgewerkt (regisseur, centraal)
