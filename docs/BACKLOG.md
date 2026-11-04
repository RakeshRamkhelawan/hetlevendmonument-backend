# SanskritiSetu Backlog — Single Source of Truth

> **Last audit:** 2026-07-29
> **Owner:** Rakesh Ramkhelawan
> **Review cadence:** Bij elke sprint-afsluiting of Gate 2/3 besluit
> **Previous version:** 2026-04-13 (v6) — volledig herschreven

---

## Hoe dit document te gebruiken

- **P0**: Blokkeert productie of compliance. Start onmiddellijk.
- **P1**: Belangrijk voor roadmap of architectuur. Inplannen volgende sprint.
- **P2**: Nuttig maar niet blokkerend. Backlog voor toekomstige sprint.
- **Status onzeker**: Bronnen conflicteren of zijn verouderd. Vereist triage.
- ~~Doorgestreept~~: Afgerond, met commit-referentie en datum.

---

## 0. Afgerond sinds v6 (2026-04-13 t/m 2026-07-15)

### 0.1 Test Suite Stabilisatie & CI Herstel

| Sprint | Beschrijving | Eindresultaat | Datum |
|--------|-------------|---------------|-------|
| ~~SP-CI-001~~ | CI Pipeline Herstel (7 dagen) | 331 Any→0, 68 mypy→0, 3 CVE→0, 4 frontend failures→0 | 2026-07-15 |
| ~~SP-SEC-001~~ | Cache Tenant Isolatie + Audit Middleware + JSON Hardening | 13.310/0 unit tests, 3 arch tests GROEN | 2026-07-01 |
| ~~SP-SEC-002~~ | API Response Conformance + Paginering + BudgetManager Wiring | BE-SVC-052/053 + FE-PGS-030 APPROVED | 2026-07-01 |
| ~~SP-AUDIT-003~~ | AuditService best_effort + transactie-semantiek | BE-AUD-001/002 APPROVED, 0 regressies | 2026-06-30 |
| ~~SP-AUDIT-004~~ | Audit log wiring + PII-sanering + tenant guard | BE-AUD-003/004/005 APPROVED, 793 regressie GROEN | 2026-06-30 |

### 0.2 DLP & GDPR Enforcement

| Sprint | Beschrijving | Eindresultaat | Datum |
|--------|-------------|---------------|-------|
| ~~SP-DLP-001~~ | DLP kern (5 dagen) | 8 CRITICAL + 44 HIGH bevindingen gesloten | 2026-06-26 |
| ~~SP-DLP-002~~ | GovernanceContract + LawfulBasisRegistry + forget-me + profiling | 4 dagen, 16 TDD tests GROEN | 2026-06-26 |
| ~~SP-DLP-003~~ | LawfulBasisRegistry hard-blocking + per-request consent + hash chain | 4 dagen, alle arch tests GROEN | 2026-06-26 |
| ~~SP-DLP-004~~ | Hash chain in ai_transparency_service + cookie_consent | 1 dag, 595 gov tests GROEN | 2026-06-26 |
| ~~SP-DLP-005~~ | request_human_review tenant_id=0 fix + hash chain | 1 dag, 5/5 arch tests GREEN | 2026-06-26 |

### 0.3 Agent Runtime & CriticAgent

| Sprint | Beschrijving | Eindresultaat | Datum |
|--------|-------------|---------------|-------|
| ~~SP-AGT-005~~ | CriticAgent PostgreSQL + orphaned methoden + structured JSON | 3 dagen, BE-AGT-017 APPROVED | 2026-06-19 |
| ~~SP-AGT-006~~ | CriticAgent Tier-1 + Judge Panel + Telemetrie | 3 dagen, BE-AGT-018/019/020 APPROVED | 2026-06-27 |
| ~~SP-AGT-007~~ | CriticAgent Prometheus + HITL + LearningMixin + CritiqueChart | 1 dag, BE-AGT-021/022/023 + FE-CMP-038 | 2026-06-27 |
| ~~SP-AGT-008~~ | ShadowCEO Check 6 + OODALoopObserver Orient/Decide | 1 dag, 11/11 tests GROEN | 2026-06-28 |
| ~~SP-AGT-009~~ | TwinEventBridge CritiqueScoreLow handler + EvalHarness | 3 dagen, BE-AGT-026/028 APPROVED | 2026-06-28 |
| ~~SP-AGT-010~~ | CriticAgent hardening: YAML hot-reload + provider-diversiteit | 3 dagen, BE-AGT-027/029 APPROVED | 2026-06-28 |
| ~~SP-ADR023~~ | WorkflowService DDD-laag wiring (P0-4/P0-5) | 2 dagen, 9 TDD tests GROEN | 2026-06-27 |
| ~~SP-ADR023-002~~ | Agent-discovery + Redis-cache + Prometheus-metrics | 3 dagen, 903/0 regressie GROEN | 2026-07-06 |

### 0.4 Frontend & Architectuur

| Sprint | Beschrijving | Eindresultaat | Datum |
|--------|-------------|---------------|-------|
| ~~SP-FE-2F~~ | Phase 2 Visual Redesign (Prana + Shadow CEO + A2A) | 14 items, 3 Vitest shards GROEN | 2026-06-29 |
| ~~SP-FE-2G~~ | Phase 2 Visual Redesign (Digital Twin + Traces + CollaborationCanvas) | 24 items CLOSED, ADR-028 9/9 DONE | 2026-07-01 |
| ~~FE-AUTH-001~~ | Frontend Auth Debt (M1-M9) | 63min→10min vitest, 0 errors | 2026-06-20 |
| ~~SP-API-011~~ | ADR-033 import consolidatie (3 dagen) | 294 arch tests, 0 xfailed | 2026-06-27 |
| ~~AUDIT-DB-01~~ | Routers injecteren geen directe AsyncSession (ADR-033 pilot) | 16 unit + 1 arch test GROEN | 2026-06-28 |
| ~~SP-TYPE-006~~ | Type-Hardening Sprint (Security & Governance Boundaries) | 33 tests GROEN, TS 0 errors | 2026-06-27 |
| ~~AUDIT-ST-DB01~~ | Single-tenant DB audit (S1-S7) | 16/16 bevindingen PASS, ADR-035 Accepted | 2026-07-02 |
| ~~Multidiscip. Audit~~ | 10-discipline audit (6 CRITICAL, 3 HIGH, 11 MEDIUM, 4 LOW) | 9/9 ADR-028 DONE, 4 disciplines GROEN | 2026-06-30 |

### 0.5 AI Act 2026 Governance Program

| Component | Status | Datum |
|-----------|--------|-------|
| ~~6 Sprints (S1-S6)~~ | 30 evidence records, 40/40 matrix closure, alle P0 gaps closed | 2026-06-30 |
| ~~Post-audit gap fixes~~ | 6 critical gaps gefixed (CVA/FB/ALS/Agentic/WS) | 2026-06-30 |
| ~~ADR-031~~ | Program GO — canonical pipeline + autonomy ladder L1-L4 | 2026-06-30 |

### 0.6 Digital Twin (ADR-025)

| Component | Status | Datum |
|-----------|--------|-------|
| ~~OODA-loop observer pipeline~~ | Gebouwd + batch persistence | 2026-06-28 |
| ~~GDPR export/delete~~ | Compleet | 2026-06-28 |
| ~~LLM struggle analysis~~ | EvalHarness BE-AGT-028 APPROVED | 2026-06-28 |
| ~~TwinEventBridge~~ | CritiqueScoreLow handler (gap #2) GESLOTEN | 2026-06-28 |
| ~~ADR-025 gap #1~~ | GESLOTEN (SP-AGT-008) | 2026-06-28 |
| ~~ADR-025 gap #2~~ | GESLOTEN (SP-AGT-009) | 2026-06-28 |
| ~~ADR-025 gap #3~~ | Post-MVP (Act-fase) | — |

---

## 1. Actueel — Open en Bevestigd

### 1.1 ADR-036 Fundament — Audit-to-Fix Sprint (P0/P1)

**Bron:** `docs/agent-briefs/generated/2026-07-03-audit-to-fix-adr036-fundament.md`
**Status:** Dag 1 (AUDIT-003) afgerond, Final Approver pending bevestiging. Dagen 2-7 nog open.

| ID | Titel | Prioriteit | Status | Bestand(en) | Commit (indien af) |
|----|-------|-----------|--------|-------------|-------------------|
| AUDIT-003 | Cleanup-gat tenant-ContextVar bij falende agent-instantiatie | P1 | **Dag 1 DONE, FA pending** | `src/core/tasks/workflow_tasks.py` | `dacc3af5` |
| AUDIT-004 | Twin-geheugen heeft geen echte verwijdering (GDPR art. 17) | **P0** | OPEN | `src/domains/memory/services/memory_write_service.py:206-219` | — |
| AUDIT-007 | ToolBrokerAdapter hardcodet "copilot", blokkeert D1 | P1 | OPEN | `src/core/copilot/council/factory.py:127-138` | — |
| AUDIT-008 | 0 permissieprofielen voor 135/136 ALS-skills | P1 | OPEN | `config/tool_permissions.yml` | — |
| AUDIT-009 | DomainPackOrchestrator._execute_step is placeholder | P1 | OPEN | `src/core/als/enterprise/packs.py:283-291` | — |

**Dependency-graaf:** AUDIT-008 → AUDIT-009 (009 kan pas na 008). Rest is standalone.

**Planned fix-sprint (7 dagen):**
- Dag 1: AUDIT-003 ✅ (afgerond)
- Dag 2: AUDIT-007
- Dag 3: AUDIT-004
- Dag 4: AUDIT-008
- Dag 5: AUDIT-009
- Dag 6: Verificatie alle 5 bevindingen
- Dag 7: Re-audit + preventie + ADR-036-update

---

### 1.2 API Response Conformance — BP-001 (P1)

**Bron:** `.claude/WORKING-CONTEXT.md:10` + `tests/architecture/test_api_response_format_conformance.py`
**Status:** CI-blokkering actief. Arch test ROOD.

| # | Item | Prioriteit | Details |
|---|------|-----------|---------|
| BP-001 | 248 non-conformante API response wrappers in 4 router files | P1 | `tests/architecture/test_api_response_format_conformance.py` scant `@router.*` handlers op missing `success/data`-wrapper. Huidige scope: 4 bestanden in `ROUTER_FILES_SCOPE`. |

**Huidige scope (4 router bestanden):**
- `src/core/api/v1/agents/agent_crud_router.py`
- `src/core/api/v1/company/external_agent_router.py`
- `src/core/api/v1/notifications/notifications_router.py`
- `src/core/api/v1/workflow/workflow_router.py`

---

### 1.3 ADR-029 — Foundation Portal (P1)

**Bron:** `docs/agent-briefs/generated/2026-07-27-adr029-backend-implementatieplan.md`
**Status:** Planning fase — Gate 1 (scope definitie). Implementatieplan klaar, wacht op Rakesh GO.

| Fase | Omschrijving | Dagen | Status |
|------|-------------|-------|--------|
| Fase 0 | ID toewijzing + feature docs | 0.5 | Klaar (21 IDs toegekend) |
| Fase 1 | Model uitbreidingen + Alembic migratie | 1 | Niet gestart |
| Fase 2 | Router structuur | 0.5 | Niet gestart |
| Fase 3 | Endpoint implementatie (21 endpoints) | 3 | Niet gestart |
| Fase 4 | Auth integratie + OAuth2 scopes | 1.5 | Niet gestart |
| Fase 5 | Testing + validatie | 1.5 | Niet gestart |
| **Totaal** | | **~8 dagen** | **Wacht op Gate 1 GO** |

**Belangrijkste ontbrekende componenten:**
- ❌ 21 API endpoints (`/api/v1/{tenantSlug}/foundation/...`)
- ❌ `foundation` registry in `router_registry.py`
- ❌ OAuth2 scopes: `portal:read`, `portal:upload`, `portal:admin`, `portal:curate`, `portal:edu`
- ❌ `FoundationContent` velduitbreiding (`lat`, `lng`, `location_name`, `license`, `category`, `metadata`, `status`, `moderated_at`, `moderated_by`)
- ❌ Nieuwe modellen: `EducationalAccess`, `StudyCollection`
- ❌ Magic link flow (stateless tokens, 15 min expiry)
- ❌ OAI-PMH endpoint (Dublin Core)

---

### 1.4 Pre-existing Test Failures (P2)

**Bron:** `.claude/WORKING-CONTEXT.md:58-61`
**Status:** Bekend, niet geintroduceerd door recente sprints. Vereist aparte sprint of fix.

| # | Item | Bestand | Context |
|---|------|---------|---------|
| DSM011 | `test_dsm_011_governance_instability_below_0_40` faalt | `tests/architecture/` | Pre-existing sinds 2026-07-07. governance I=0.306 (Grade A+ behaald), maar test faalt. |
| DSM-ARCH-6 | 6 pre-existing DSM-architecture-testfalen | `tests/architecture/` | governance<->agent_runtime koppeling. Git blame: 2026-07-07. Vermoedelijk samenhangend met GDPR-sprint. |

---

### 1.5 Bekende CI Uitzonderingen (P2 — Bewust geaccepteerd)

**Bron:** `.claude/WORKING-CONTEXT.md:47-51`
**Status:** Geen actie nodig tot eigenaar (GDPR-sprint) deze oplost.

| Tool | Aantal | Bestanden | Eigenaar |
|------|--------|-----------|----------|
| mypy | 5 fouten | 3× `dsar_service.py` + 2× `events_router.py` | GDPR-sprint |
| pyright | 5 fouten | 2× `dsar_service.py` + 2× `events_router.py` + 1× `audit_endpoints.py` | GDPR-sprint |

**Nota:** `continue-on-error: true` verwijderd uit CI op 2026-07-15 (Rakesh GO). Beide stappen falen nu bewust rood op deze uitzonderingen.

---

### 1.6 Main-promotie (P1)

**Bron:** `.claude/WORKING-CONTEXT.md:63`
**Status:** Bewust uitgesteld door Rakesh (2026-07-13). Apart open item.

| # | Item | Besluit nodig |
|---|------|--------------|
| MAIN-001 | Promotie `develop` → `main` | Rakesh GO vereist. SP-CI-001 is CLOSED. 6 pre-existing DSM-failures moeten worden beoordeeld of ze main-promotie blokkeren. |

---

### 1.7 In-Code TODO Markers (P2)

**Bron:** Codebase scan 2026-07-29
**Telling:** ~28 bestanden met `TODO(SP-VOLGENDE)` of vergelijkbare markers.

| Categorie | Aantal bestanden | Voorbeelden |
|-----------|-----------------|-------------|
| Router/endpoint TODOs | 8 | `agent_endpoints.py`, `billing_endpoints.py`, `webhook_endpoints.py`, `swarm_websocket_endpoints.py` |
| Service-layer TODOs | 6 | `bm25_service.py`, `rbac_service.py`, `dsar_service.py`, `cva_service.py` |
| Agent/TODOs | 5 | `autonomous_agent.py`, `agent_router_agent.py`, `master_orchestrator_agent.py` |
| Test/architectuur TODOs | 4 | `test_gap_fixes.py`, `test_cva_council_wiring.py` |
| Overig | 5 | `main.py`, `app_factory.py`, `events_router.py` |

**Volledige lijst:** `grep -r "TODO(SP-VOLGENDE)" src/ tests/`

---

### 1.8 SOC 2 Readiness — Trigger-gebaseerd (P2)

**Bron:** `docs/compliance/soc2/README.md` + `.claude/WORKING-CONTEXT.md:473-477`
**Status:** Controls grotendeels GEREED. Openstaande items zijn trigger-gebaseerd.

| Trigger | Item | Prioriteit | Status |
|---------|------|-----------|--------|
| D-7 productie-lancering | MFA bewijs-screenshots toevoegen | P2 | Wacht op lanceringsdatum |
| Eerste tenant onboarding | Kwartaallijks access review | P2 | Wacht op eerste tenant |

---

### 1.9 Codeformattering -- geen gate, geen eenduidige formatter (P2)

**Bron:** onafhankelijke hercontrole ADR-036 Fase 2, 2026-08-02 (BE-AGT-043, commit `c36411de`)
**Status:** Symptoom afgevangen, oorzaak open. Vraagt een besluit van Rakesh.

Formattering wordt door **geen enkele gate** afgedwongen. `scripts/ci-local-fast.sh` (de
pre-push gate) draait alleen `ruff check` -- de linter. `E501` staat in `pyproject.toml`
expliciet uit met de reden "enforced by black formatter separately", maar black is nergens
een poort en geen actieve CI-workflow controleert opmaak.

Daar komt bij dat er **twee formatters in omloop zijn die het niet eens zijn**: `make format`
gebruikt black + isort, terwijl `scripts/run_ci_locally.ps1:68` `ruff format --check` draait.
Ze verschillen onder meer op een comment in een parameterlijst.

**Meting 2026-08-02 op `develop`:**

| Wat | Aantal |
|-----|--------|
| Bestanden in `src/` niet black-schoon | 810 van 2211 |
| Bestanden in `src/` niet ruff-format-schoon | 704 van 2211 |
| Regels langer dan 100 tekens | 2985 |

**Waarom dit pijn deed:** een formatter loslaten op een nooit-geformatteerd bestand
herschrijft tientallen regels die de auteur niet heeft aangeraakt. Dat maakte twee commits in
ADR-036 Fase 2 onreviewbaar -- een met 70 ongerelateerde bestanden (84 gewijzigd terwijl er 15
van de auteur waren) en een wijziging die alleen emoji verwijderde maar drie functiesignaturen
meenam.

| # | Item | Besluit nodig |
|---|------|--------------|
| FMT-001 | Kies EEN formatter voor het hele project: black + isort (zoals `make format`) of `ruff format` (zoals `run_ci_locally.ps1`). Nu staan beide in de repo | Rakesh GO |
| FMT-002 | Eenmalige repo-brede normalisatie met die formatter. Diff van ~800 bestanden, raakt iedereen die parallel werkt -- eigen commit, rustig moment, geen feature-sprint | Rakesh GO + timing |
| FMT-003 | Pas daarna: formattering als blokkerende CI-stap, en `E501` weer aanzetten in `pyproject.toml` | Volgt op FMT-002 |

**Al afgevangen (geen actie meer nodig):** `.claude/hooks/format-on-save.sh` formatteert sinds
2026-08-02 alleen nog als de GECOMMITTE versie van het bestand al schoon is. Nieuwe bestanden
wel. Daardoor kan een edit geen ongerelateerde code meer herschrijven, ook zolang FMT-001 t/m
FMT-003 openstaan. Regels en meetmethode staan in `.claude/rules/quality-gates.md`.

**Valkuil bij het oppakken:** meet opmaakschuld altijd BINNEN de repo. Een kopie in `C:/tmp`
laat de formatter zijn eigen default gebruiken in plaats van `pyproject.toml`; dat leidde bij
de eerste diagnose tot de onjuiste conclusie dat de hook op regellengte 88 stond (beide staan
op 100). Correct: `git show HEAD:<pad> | python -m ruff format --check --stdin-filename <pad> -`

---

### 1.10 DEPLOY-001 -- twee GitHub-secrets aanmaken (P0, actie Rakesh, geen code)

**Vastgelegd 2026-08-03 (BE-AGT-045, ADR-036 OP-27). Blokkeert elke deploy tot het gedaan is --
met opzet.** Dit is geen ontwikkelwerk maar een eenmalige handeling in GitHub.

```bash
gh secret set STAGING_TOOL_PAYLOAD_PSEUDONYM_KEY --body "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
gh secret set PROD_TOOL_PAYLOAD_PSEUDONYM_KEY    --body "$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

| Wat | Waarom |
| --- | --- |
| Twee VERSCHILLENDE waarden | Dezelfde sleutel in staging en productie betekent dat wie staging kan lezen de productielogs kan terugrekenen |
| Minimaal 32 tekens | Korter is offline te kraken; de opstartcontrole weigert het en de deploy stopt |
| Minimaal 8 VERSCHILLENDE tekens | Sinds 2026-08-05 (`key_strength_problem()`). `secrets.token_urlsafe(32)` haalt dit altijd; met de hand verzonnen sleutels als `aaaa...` niet |
| Geen herhaald blok | `"changeme" * 6` of een projectnaam vier keer achter elkaar wordt geweigerd, ook afgekapt |

**LET OP -- de sterkte-eis is verscherpt NA het aanmaken van de sleutels (Gate 2 ronde 6, F9c).**
De twee secrets bestaan al (aangemaakt 2026-08-04, waarden op het bureaublad; zie de
overdrachtsdocumenten). De boot-check controleerde toen alleen de LENGTE. Nu weigert hij ook op
aantal verschillende tekens en op blokherhaling.

`check_secret` in CD toetst alleen AANWEZIGHEID, niet sterkte. Een bestaande sleutel die de nieuwe
eis niet haalt geeft dus een groene deploy en een container die bij het opstarten stopt. Controleer
beide waarden EEN keer voordat er gedeployed wordt:

```bash
python -c "import sys; sys.path.insert(0,'.'); import os; os.environ['ENVIRONMENT']='test'; \
from src.core.tool_broker.redaction import key_strength_problem; \
print(key_strength_problem(input('sleutel: ')) or 'OK')"
```

Zijn ze met `secrets.token_urlsafe(32)` gegenereerd zoals hierboven voorgeschreven, dan is dit een
formaliteit -- gemeten: die generator wordt nooit geweigerd. Is een van de twee met de hand
gemaakt, dan moet hij vervangen worden VOORDAT de eerste digest is weggeschreven; daarna kan het
niet meer zonder al het eerdere bewijs onbruikbaar te maken.
| Daarna NOOIT wijzigen | Deze sleutel maakt de vastgelegde kenmerken in de ADR-019 auditketen narekenbaar. Verandert hij, dan is al het eerdere bewijs onbruikbaar -- en dat spoor is waarmee AI Act art. 12(2) toezicht mogelijk maakt |
| Ook buiten GitHub bewaren | Er is geen tweede kopie; de waarden staan NERGENS in deze repo en dat hoort zo |

Wat er gebeurt als je het overslaat: CD stopt bij de secret-check met een expliciete melding.
Dat is de bedoeling -- het alternatief was een backend die opstart en daarna elke tool-aanroep
weigert, en dat is een stille storing.

Zodra beide secrets bestaan: dit item afvinken en het blok bovenaan
`.claude/WORKING-CONTEXT.md` verwijderen.

---

## 2. Status Onzeker — Triage Nodig

### 2.1 SP-API-009 — Forbidden Imports Afsluiten

**Bron:** `docs/SPRINT-CANVAS.md:15-28` beweert "IN PROGRESS"; `docs/SPRINT_TRACKER.md` + `.claude/WORKING-CONTEXT.md` vermelden SP-API-011 (niet 009) als CLOSED.
**Status:** Conflicterend. SPRINT-CANVAS (2026-07-06) zegt 249 forbidden imports met DSM stand IN PROGRESS.

| # | Item | Conflicterende bron |
|---|------|-------------------|
| T1 | 249 forbidden imports resterend (doel: < 200) | SPRINT-CANVAS zegt IN PROGRESS; WORKING-CONTEXT zegt SP-API-011 CLOSED |

**Aanbevolen actie:** Verifieer huidige DSM-stand. Run `tests/architecture/test_dsm_*.py` om actuele violation-count te bepalen.

---

### 2.2 Oude Backlog Items (uit v6, status onbekend)

De volgende items uit backlog v6 (2026-04-13) zijn **niet expliciet als afgerond geverifieerd** in recente sprints:

| # | Item | Oude prioriteit | Status v6 |
|---|------|-----------------|-----------|
| E1 | `goal_alignment.py` verwijderen of gebruiken | Low | Onbekend |
| E2 | `context.py` volledig integreren | Medium | Onbekend |
| E3 | Pack activation performance (caching layer) | Medium | Onbekend |
| E4 | Org chart virtual scrolling (10K+ nodes) | High | Onbekend |
| F1 | OpenTelemetry tracing voor pack-selector | P1 | Onbekend |
| F2 | Storybook documentatie pack-selector | P2 | Onbekend |
| F3 | E2E tests pack-selector flow | P1 | Onbekend |
| G1 | Integration tests voor 4 feature-gaps (20 tests) | P1 | Onbekend |
| G2 | Two-way notifications (inbound IMAP/SMS/webhooks) | P2 | Onbekend |
| G4 | Canvas specificatie | P3 | Onbekend |

**Aanbevolen actie:** Cross-reference met huidige codebase. Items die opgelost zijn → sectie 0. Resterende → sectie 1 of 2.

---

## 3. Post-MVP / Gearchiveerd

| # | Item | ADR | Reden |
|---|------|-----|-------|
| PMV-001 | Event Sourcing met state projection | ADR-018 | Post-MVP — ADR-019 audit voldoende voor launch |
| PMV-002 | RC-009b: Paginering/OTel/response envelopes | — | Permanent backlog, geregistreerd in SPRINT_PLANNING.md |
| PMV-003 | ADR-025 gap #3: Digital Twin Act-fase | ADR-025 | Post-MVP — Observe/Orient/Decide gebouwd, Act pending |

---

## Tellingen

| Categorie | Items | Opmerking |
|-----------|-------|-----------|
| **0. Afgerond** | 35+ sprints/features | April–Juli 2026 |
| **1.1 ADR-036** | 4 open (AUDIT-004/007/008/009) | 1 DONE pending FA |
| **1.2 BP-001** | 1 open | CI-blokkering |
| **1.3 ADR-029** | 1 open (wacht Gate 1 GO) | 21 endpoints |
| **1.4 Pre-existing** | 2 open | DSM-tests |
| **1.5 CI uitzonderingen** | 2 bekende | Bewust geaccepteerd |
| **1.6 Main-promotie** | 1 open | Rakesh besluit |
| **1.7 TODO markers** | ~28 bestanden | SP-VOLGENDE |
| **1.8 SOC 2** | 2 trigger-items | Wacht op lancering/onboarding |
| **1.9 Formattering** | 3 open (FMT-001/002/003) | Rakesh besluit; symptoom al afgevangen |
| **2. Triage** | 2 clusters + 10 oude items | Verificatie nodig |
| **3. Post-MVP** | 3 items | Gearchiveerd |

---

## Changelog

| Datum | Actie |
|-------|-------|
| 2026-03-29 | Initieel document (v1) |
| 2026-03-30 | v4: 29 items afgerond, sectie 0 toegevoegd |
| 2026-04-09 | v5: Test suite stabilisatie afgerond |
| 2026-04-13 | v6: Frontend Auth Debt Audit toegevoegd (M1-M9) |
| **2026-08-02** | **v8:** sectie 1.9 toegevoegd -- codeformattering is geen gate en er zijn twee concurrerende formatters (810/2211 bestanden niet black-schoon). Symptoom afgevangen in de save-hook; FMT-001/002/003 wachten op besluit Rakesh. |
| **2026-07-29** | **v7: Volledige herschrijving.** Alle sprints april–juli 2026 naar sectie 0. ADR-036, BP-001, ADR-029, pre-existing failures, CI-uitzonderingen, TODO-markers, SOC 2 triggers toegevoegd. Oude items (E1-E4, F1-F3, G1-G4) naar triage verplaatst wegens onverifieerde status. |
