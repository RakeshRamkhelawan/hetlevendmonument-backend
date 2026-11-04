# AI Collaboration Workflow

> **Single source of truth** voor AI agents die aan SanskritiSetu ontwikkelen.
>
> Dit document beschrijft de algemene werkwijze die in elke iteratie van toepassing is,
> ongeacht het domein (frontend, backend, Co-Pilot, integratie) of de specifieke ADR.
>
> **Eigenaar:** Rakesh Ramkhelawan
> **Laatste update:** 2026-05-27 (review + fixes door Claude)

---

## 1. Bronhiërarchie

Bij conflict tussen bronnen geldt deze volgorde (hogere nummers wijken bij conflict):

| Rang | Bron | Waarom bindend |
|------|------|----------------|
| 1 | `CLAUDE.md` (repo root) | Projectbrede conventies, kwaliteitsloop, niet-onderhandelbare regels |
| 2 | Specifiek ADR voor deze iteratie | Architectuurbeslissingen voor het huidige domein |
| 3 | Domein-specifieke guardrails | Frontend: `docs/copilot-phase-2-frontend-visual-redesign/GUARDRAILS.md` / Backend: type-strict + tenant-isolatie |
| 4 | Domein-specifieke review gates | `docs/copilot-phase-2-frontend-visual-redesign/REVIEW_GATES.md` (frontend) of kwaliteitsloop (backend) |
| 5 | De iteratie-specifieke dag-template | Concrete taken, acceptatiecriteria, valkuilen |
| 6 | Bestaande codebase-patronen | Consistentie met reeds geïmplementeerde code |

**Als twee bronnen elkaar tegenspreken zonder oplossing:**
> **Stop, schrijf geen productiecode en rapporteer de blocker expliciet aan Rakesh.**

---

## 2. Het 5-Stappen Dagritme

Elke ontwikkeldag volgt hetzelfde ritme, ongeacht het domein:

```text
Stap 1: CONTEXT       → Lees bindende documenten en vorige iteratie-output
Stap 2: ONDERZOEK     → Inventariseer codebase: Glob + Grep + Read (min. 5 referenties)
Stap 3: BESLISSEN     → Leg minimaal 3 architectuurbeslissingen vast met motivatie + regressie-impact
Stap 4: BOUWEN        → Implementeer met kwaliteitsloop (review → test → write)
Stap 5: DOCUMENTEREN  → Genereer feature-spec + review + update ID-REGISTRY
```

### Stap 1 — Context

**Altijd eerst lezen (in volgorde):**

1. `CLAUDE.md` — Bindende projectregels
2. Het ADR dat bij deze iteratie hoort (bijv. ADR-027 voor Co-Pilot, ADR-028 voor Frontend)
3. De domein-architectuur (bijv. `docs/copilot-architecture.md`, `docs/frontend-architecture.md`)
4. De iteratie-specifieke dag-template of masterprompt
5. De output van de vorige dag (dat is de input voor vandaag)

**Als een verplicht bestand ontbreekt:** noteer als blocker, maak geen aannames.

### Stap 2 — Onderzoek

**Voor elke taak:**

1. `Glob` op verwachte paden
2. `Grep` op trefwoorden (class names, patronen)
3. `Read` minstens 2 vergelijkbare bestanden
4. Noteer **exacte paden + regelnummers** van patronen die gevolgd moeten worden

**Minimum norm:** 5 concrete referenties met pad en regelnummer.
**Streefwaarde:** 8 of meer voor complexere taken.

### Stap 3 — Beslissen

**Leg minimaal 3 architectuurbeslissingen vast:**

- Onderzochte patronen (met pad:regel referenties)
- Gekozen aanpak (1 zin)
- Motivatie (2-4 zinnen)
- Afgewezen alternatief (waarom niet)
- Regressie-impact (hoeveel call-sites geraakt, hoe gemeten)

**Als er minder dan 3 beslissingen zijn:** het onderwerp is te triviaal of onvoldoende onderzocht.

### Stap 4 — Bouwen

**Pas NA de kwaliteitsloop schrijf je code.** Zie sectie 3 (Review Lagen).

**Verplichte volgorde vóór elke Write/Edit (niet onderhandelbaar):**

```text
1. Code review       → onafhankelijke subagent (architectuur, ADR-naleving, codebase-patronen)
2. Quality review    → onafhankelijke subagent (linting, types, secrets, OWASP)
3. Happy path tests  → schrijf vóór implementatie
4. Unhappy path tests → schrijf vóór implementatie
5. Behavioral tests  → minimaal 1 vanuit gebruikersperspectief
6. Integratietests   → altijd tegen echte backend (geen mocks, geen stubs) — per fase
→ PAS DAN: code wegschrijven
```

Een agent die zichzelf reviewt voldoet **niet** aan stap 1 en 2. Gebruik de Agent-tool met een afzonderlijke subagent.

**Per write:**
- Format met black (Python, 100 chars) of Prettier (TypeScript)
- Sorteer imports (isort / ESLint)
- Lint (ruff / ESLint)
- Check op security (bandit)

### Stap 5 — Documenteren

**Elke iteratie die output oplevert, is pas KLAAR als feature-docs bestaan:**

| Stap | Actie | Output |
|------|-------|--------|
| 5a | Genereer feature-spec via builder prompt | `docs/<domein>/features/<ID>-<naam>.md` |
| 5b | Voeg Trainingssamenvatting toe aan spec: minimaal 1 flow met Actor / Voorwaarde / Actie / Systeemreactie / Succesrespons / Foutrespons / Uitzonderingen | Onderdeel van spec-bestand |
| 5c | Review spec via reviewer prompt | `docs/<domein>/review/review-<ID>.md` |
| 5d | Fix CRITICAL/HIGH findings, herhaal indien nodig | Geüpdatete spec |
| 5e | Registreer ID in ID-REGISTRY | `docs/<domein>/features/ID-REGISTRY.md` |
| 5f | Maak user guide / integratorhandleiding | `docs/user-guide/<domein>/<naam>.md` |

**Sprint dag is pas KLAAR als:**
- Alle specs op APPROVED of APPROVED WITH MINOR GAPS staan
- Geen CRITICAL of HIGH issues open
- Elke spec bevat een Trainingssamenvatting (Actor / Voorwaarde / Actie / Systeemreactie / Succesrespons / Foutrespons / Uitzonderingen)
- `python scripts/validate_feature_docs.py` → exit code 0 (verplicht voor frontend-iteraties)
- Status-tabel is bijgewerkt

---

## 3. Review Lagen (A / B / C)

### Laag A — Per Code-Write (vóór elke Write/Edit)

**In deze volgorde, zonder overslaan:**

1. **Code review** *(onafhankelijke subagent)* — Architectuur, ADR-naleving, CLAUDE.md patronen, bestaande codebase-patronen
2. **Quality review** *(onafhankelijke subagent)* — Linting, type checking, formatting, import structuur, hardcoded secrets
3. **Security review** — OWASP top 10, XSS, CSS injection, tenant isolation, scope bypass
4. *(Frontend only)* **Accessibility review** — WCAG AA, keyboard navigatie, ARIA, contrast

Reviews 1 en 2 **moeten** via een afzonderlijke Agent-tool subagent worden uitgevoerd. Zelfbeoordeling telt niet.

**Resultaat per review:** APPROVED / NEEDS REVISION / BLOCKED

**Als BLOCKED:** stop alle writes voor de rest van de dag. Fix het onderliggende probleem. Herhaal de review. Begin pas schrijven na APPROVED.

### Laag B — Per Dag-Afsluiting

**Over de hele dag-output:**

1. **Performance review** — Re-renders, bundle impact, lazy loading, memory leaks
2. **UX/UI consistency review** — Consistente spacing, kleuren, interactiepatronen
3. **Design system review** — Token-gebruik, dark mode, geen hardcoded waarden

**Dag is KLAAR als:** alle 3 APPROVED.

### Laag C — Per Sprint-Afsluiting (dag 5)

**Over de volledige sprint-output:**

1. **Compatibility review** — Cross-browser, responsive, touch-targets
2. **Privacy/compliance review** — PII classificatie, logging, opslag, export, consent
3. **Release readiness review** — Debug artefacten, TODO markers, hardcoded waarden, test-contaminatie

**Sprint is KLAAR als:** 3x GO.

---

## 4. Feature Documentatie Workflow

### Algemene 3-staps structuur

Stap 1: **BUILD** → Genereer spec via builder prompt
Stap 2: **REVIEW** → Review spec via reviewer prompt
Stap 3: **GO** → Fix findings, sla op, registreer ID

### Domein-specifieke implementaties

| Domein | ID-prefix | Spec locatie | Review locatie | Template |
|--------|-----------|-------------|----------------|----------|
| Frontend | `FE-xxx` | `docs/frontend/features/` | `docs/frontend/review/` | `docs/copilot-phase-2-frontend-visual-redesign/FEATURE_DOC_WORKFLOW.md` |
| Backend | `BE-xxx` | `docs/backend/features/` | `docs/backend/review/` | `docs/backend/FEATURE_DOC_WORKFLOW.md` |
| Toekomstig | `<prefix>-xxx` | `docs/<domein>/features/` | `docs/<domein>/review/` | `docs/<domein>/FEATURE_DOC_WORKFLOW.md` |

### Unieke ID-conventie (generiek)

- `<PREFIX>-PAGE-###` — Pagina / route
- `<PREFIX>-EP-###` — Endpoint
- `<PREFIX>-SVC-###` — Service
- `<PREFIX>-MDL-###` — Model
- `<PREFIX>-SCH-###` — Schema
- `<PREFIX>-CMP-###` — Component
- `<PREFIX>-HK-###` — Hook
- `<PREFIX>-UTL-###` — Utility
- `<PREFIX>-FLW-###` — Flow
- `<PREFIX>-SEC-###` — Security wrapper

**Altijd ID-REGISTRY controleren voordat een nieuw ID wordt toegewezen.**

---

## 5. Definition of Done per Iteratietype

### Foundation-iteratie (componenten, design system, utilities)

- [ ] Alle deliverables in output-contract aangemaakt
- [ ] Laag A: 3x APPROVED (backend) of 4x APPROVED (frontend, inclusief Accessibility)
- [ ] Laag B: 3x APPROVED
- [ ] `test:unit` — 0 failures
- [ ] `type-check` — 0 errors
- [ ] Behavioral tests: minimaal 1 per nieuw interactief element
- [ ] Feature-specs: 1 per component/hook/utility, elk met Trainingssamenvatting
- [ ] Reviews: APPROVED of APPROVED WITH MINOR GAPS, geen CRITICAL/HIGH open
- [ ] ID-REGISTRY bijgewerkt

### Pagina-iteratie (pagina's, features, flyouts)

- [ ] Alle deliverables in output-contract aangemaakt
- [ ] Laag A: 3x APPROVED (backend) of 4x APPROVED (frontend, inclusief Accessibility)
- [ ] Laag B: 3x APPROVED
- [ ] `test:unit` — 0 failures
- [ ] `type-check` — 0 errors
- [ ] Behavioral tests bijgedragen aan sprint-minimum (>=10 totaal per sprint)
- [ ] Feature-specs aangemaakt, elk met Trainingssamenvatting, gereviewd
- [ ] ID-REGISTRY bijgewerkt

### Full-stack-iteratie (backend + frontend)

- [ ] Alle deliverables aangemaakt (backend + frontend)
- [ ] Alembic check slaagt (`alembic check`)
- [ ] Alembic offline dry-run slaagt (`alembic upgrade head --sql`)
- [ ] Elke nieuwe migration heeft een werkende `downgrade()` — geen `pass`
- [ ] Backend tests: happy + unhappy + tenant-isolatie + security (`@pytest.mark.security`)
- [ ] Integratietests altijd tegen echte backend — geen mocks, geen stubs; alle services draaien (backend + DB + Redis)
- [ ] Backend Laag A: 3x APPROVED (Code + Quality + Security)
- [ ] Frontend Laag A: 4x APPROVED (inclusief Accessibility)
- [ ] `test:unit` — 0 failures
- [ ] Laag B: 3x APPROVED
- [ ] Feature-specs aangemaakt, elk met Trainingssamenvatting, gereviewd
- [ ] ID-REGISTRY bijgewerkt

### Review-iteratie (dag 5 van elke sprint)

- [ ] Laag C: 3x GO
- [ ] Geen CRITICAL of HIGH open issues
- [ ] Alle feature-specs: APPROVED of APPROVED WITH MINOR GAPS
- [ ] `type-check` — 0 errors
- [ ] Sprint-totaal behavioral tests >= 10
- [ ] Status-tabel bijgewerkt

---

## 6. Anti-Patronen (Nooit Doen)

| Anti-patroon | Waarom fout | Correctie |
|-------------|-------------|-----------|
| Code schrijven zonder kwaliteitsloop | Regressies, ongeteste code, security leaks | Loop altijd A → B → C af vóór write |
| Scope creep buiten "In scope" lijst | Sprint niet haalbaar, ongeteste code | Stick to the plan; noteer uitbreidingen voor volgende iteratie |
| Aannames maken zonder codebase-onderzoek | Inconsistente code, breaking changes | Minimaal 5 concrete referenties vóór implementatie |
| Placeholders of "tbd" in output | Onvolledige deliverables, onduidelijke scope | Concrete paden, concrete signatures, concrete acceptance criteria |
| Reviewer "in het voordeel van de auteur" beoordelen | Gemiste bugs, technische schuld | Streng zijn: als het niet expliciet staat, is het een gap |
| `any` types / `# type: ignore` zonder reden | Type safety verloren, runtime bugs | Gebruik `unknown` + type guard, of los het onderliggende probleem op |
| `npx vitest` direct op Windows (frontend) | OOM crash | Gebruik altijd `npm run test:unit` |
| `tenant_id` uit request body / query param / localStorage | Cross-tenant aanval | Altijd uit JWT / middleware / ContextVar |
| Inline styles of hardcoded hex kleuren | Design system breekt, geen tree-shaking | Tailwind classes + tokens.ts |
| F-string logging (`f"{var}"`) | Niet gestructureerd, moeilijk te parsen | `%s`-style formatting met `extra={}` |
| `datetime.now()` zonder `timezone.utc` | Tijdzone bugs | `datetime.now(timezone.utc)` |
| `asyncio` event-loop nesting / ThreadPoolExecutor zonder cleanup | Deadlocks, memory leaks | Gebruik `asyncio.gather()` of een dedicated event loop met cleanup |
| `from __future__ import annotations` in FastAPI endpoint files | `PydanticUserError: TypeAdapter is not fully defined` bij `Query(...)` type annotations | Verwijder deze import uit **alle** FastAPI endpoint files; gebruik alleen in service/domain modules |
| `@asynccontextmanager` als FastAPI `Depends()` dependency | `TypeError: '_AsyncGeneratorContextManager' object is not an async iterator` | Gebruik **plain** `async def ... yield` generators; nooit decorated contextmanagers |
| `importlib.reload()` in tests | Breekt FastAPI dependency override identity → 401/403 in volledige suite | STRICT VERBOD; directe imports altijd gebruiken |
| `autouse=True` met global state mutation | State lekt tussen tests, order-dependent failures | Gebruik function-scope fixtures met expliciete cleanup |
| Module-level imports met side effects | Side effects tijdens test collectie, flaky tests | Imports binnen fixture of test functie |
| Fail-open security adapters (`return True` op exception) | Security bypass bij failures | Altijd fail-closed (`return False`) met logging |
| `cast()` of direct return van SQLAlchemy models in FastAPI endpoints | `MissingGreenlet` bij Pydantic `from_attributes=True` serialisatie | Gebruik `ModelRead.model_validate(result)` **binnen** sessie, of `expunge()` in repository |
| Redis client zonder socket timeouts | Oneindige hangs (3+ uur) bij onbereikbare Redis | Altijd `socket_connect_timeout` + `socket_timeout` specificeren |
| `timeout_seconds` i.p.v. `reset_timeout_seconds` in circuit breaker | Circuit breaker reset nooit, tests falen stilzwijgend | Gebruik altijd `reset_timeout_seconds` |
| Mock die conditional rendert zonder stateful props | Mock rendert altijd, tests falen op DOM verwachtingen | Props doorzetten in mock: `vi.fn(({ isOpen }) => isOpen ? ... : null)` |
| `isSuccess` direct checken na `mutateAsync()` | State is asynchroon, `isSuccess` nog niet geupdate | Altijd `await waitFor(() => expect(result.current.isSuccess).toBe(true))` |
| Complexe OR/AND in `waitFor` expectations | Timeout door altijd truthy/falsy logica | Test 1 ding per keer; callback returnt boolean |
| `pytest` volledige run zonder `--stepwise` | Bij een fail loopt de hele suite door; root cause moeilijker te isoleren | Altijd `pytest --stepwise`; gebruik `--stepwise-skip` om bekende fout tijdelijk over te slaan |
| Integratietests draaien tegen mocks / stubs | Test slaagt terwijl echte integratie kapot is (zie ADR-006 post-mortem) | Altijd echte backend: PostgreSQL op 5455, Redis, alle services actief |
| `func.now()` bij concurrent ordering onder locks | `func.now()` = transactie-starttijd; identiek bij concurrency → niet-deterministische `ORDER BY` | Gebruik `func.clock_timestamp()` voor audit logs en hash chains onder `pg_advisory_xact_lock` |
| Unicode / emoji in source code (Python of TypeScript) | Encoding-fouten in Windows PowerShell, CI-logs en cross-platform workflows | ASCII-only in code, comments en strings; gebruik `[OK]` i.p.v. `✅` |
| `os.getenv("DEBUG")` voor feature flags | `DEBUG` is gereserveerd door logging-tooling en kan non-boolean waarden bevatten | Gebruik `os.getenv("APP_DEBUG", "false").lower() == "true"` |
| Audit/metrics write in hetzelfde transactieblok als primaire operatie | Als audit commit faalt, krijgt de gebruiker een 500 terwijl de primaire operatie al geslaagd was | Gebruik `async with best_effort("audit log", db_session=db):` na primaire commit |
| `_NoOpXxx` silent fallback voor compliance/audit/logging | Compliance violation: events worden stilzwijgend gedropt | `_FailClosedXxx` die exception raise; of verplichte injectie |
| Lege/tracebare IDs in error responses | Right-to-explanation wordt gebroken; incidents niet traceerbaar | Genereer UUID voor elke error response; log naar audit trail |
| Tool execution zonder pre-flight validatie | Onbekende/malicious tools worden uitgevoerd | Valideer tool bestaat/is geregistreerd vóór execute |
| LLM prompt zonder capability catalog | LLM hallucineert acties; geen platform awareness | Injecteer capability snapshot (tools, agents, endpoints) in system prompt |
| Council deliberatie zonder platform context | Officers kunnen geen informed verdicts geven | DeliberationContext moet registered_tools, agent_health, domain_packs bevatten |

---

## 7. Failure Protocol

**Als een review BLOCKED teruggeeft:**
1. Stop alle writes voor de rest van de dag
2. Analyseer de oorzaak — pas geen workaround toe
3. Fix het onderliggende probleem
4. Herhaal de review
5. Begin pas schrijven na APPROVED

**Als een iteratie de Definition of Done niet haalt:**
1. Noteer de blocker in het iteratiebestand (sectie Stopvoorwaarden)
2. De iteratie schuift door naar de volgende sessie — sla hem NIET over
3. De volgende iteratie start NIET totdat de vorige volledig is afgevinkt

**Als een feature-spec op NEEDS REVISION blijft na 2 iteraties:**
1. Escaleer naar Rakesh met: spec-ID, reviewer-bevinding, eigen analyse
2. Ga niet door zonder toestemming

---

## 8. Hoe Toe te Passen op Nieuwe Iteraties

### Stap 1: Iteratie-template kiezen

| Iteratietype | Template | Specifieke regels |
|-------------|----------|-------------------|
| Frontend (Phase 2, ADR-028) | `docs/copilot-phase-2-frontend-visual-redesign/DAY_TEMPLATE.md` | Radix UI, Tailwind, Zustand, TanStack Query |
| Backend (Co-Pilot, ADR-027) | `docs/copilot-sprints/template.md` | FastAPI, SQLAlchemy, Pydantic, Dramatiq |
| Toekomstig domein | Kopieer bestaand template en pas aan | Nieuw ADR + nieuwe guardrails |

### Stap 2: Specifieke ADR en architectuur koppelen

Vervang in de template:
- `[ADR]` → het specifieke ADR voor deze iteratie
- `[ARCHITECTUUR]` → het specifieke architectuurdoc
- `[GUARDRAILS]` → domein-specifieke guardrails
- `[DAGTYPE]` → foundation / page / full-stack / review

### Stap 3: Feature doc workflow koppelen

Voor elke iteratie die output oplevert:
- Gebruik de juiste builder prompt (`frontend/` of `backend/`)
- Gebruik de juiste reviewer prompt
- Sla op in de juiste `docs/<domein>/` structuur
- Registreer in de juiste `ID-REGISTRY.md`

---

## 9. Samenvattende Checklist voor AI Agents

Voor elke iteratie:

- [ ] **Context gelezen:** CLAUDE.md + ADR + architectuur + vorige iteratie
- [ ] **Onderzoek gedaan:** Minimaal 5 concrete referenties met pad:regel
- [ ] **Beslissingen vastgelegd:** Minimaal 3 met motivatie + regressie-impact
- [ ] **Kwaliteitsloop Laag A:** 3x APPROVED (backend) of 4x APPROVED (frontend) vóór elke write — reviews 1+2 via onafhankelijke subagent
- [ ] **Tests geschreven:** Happy + unhappy + behavioral (min. 1); integratie tegen echte backend
- [ ] **pytest volledige run:** altijd met `--stepwise`
- [ ] **Code weggeschreven:** Geformatteerd, gelint, gecontroleerd
- [ ] **Laag B:** 3x APPROVED aan einde van de dag
- [ ] **Feature docs:** Spec + Trainingssamenvatting + review + ID-REGISTRY + user guide
- [ ] **Status bijgewerkt:** In de sprint status-tabel
- [ ] **Definition of Done:** Alle checkboxen afgevinkt

---

## 10. Lessons Learned uit Productie-Iteraties

Deze lessen komen uit concrete iteraties (P0-P7) en zijn **bindend** voor toekomstige agenten.

### 10.1 Subagent Strategie & Timeouts

| Les | Context | Toepassing |
|-----|---------|------------|
| **Complex adapter-werk heeft menselijke interventie nodig** | B3 subagent (Council factory adapters) had 60+ read calls en dreigde te timeouten door interface mismatches | Voor complexe adapter-werk met >3 service-interfaces: menselijke review verplicht vóór subagent start, of pre-verified interface signatures |
| **Regressie-test subagenten zijn minder betrouwbaar** | Shell "Start failed" errors en timeouts bij regressie-runs | Handmatige regressietests (`pytest --stepwise`) zijn betrouwbaarder dan subagent regressie-runs; gebruik subagenten alleen voor code review |
| **Parallelle subagenten versnellen binary search** | 231 test failures, binary search met 6+ parallelle agents identificeerde root cause in 30 min vs 3+ uur sequentieel | Bij >20 failures: split suite in parallelle subagenten voor snelle root cause |

### 10.2 Event Loop & Async Patterns

| Les | Root Cause | Fix |
|-----|-----------|-----|
| ThreadPoolExecutor + `asyncio.new_event_loop()` in sync adapter | Event-loop blocking + executor leaks; consent gate blokkeerde hele request | Lightweight sync adapter zonder executor; leest tenant context en returnt safe default |
| `asyncio.gather()` voor parallelle health checks | List comprehension met `await` is sequentieel; `gather()` is parallel | Altijd `asyncio.gather()` gebruiken voor onafhankelijke async calls |

### 10.3 FastAPI & Pydantic

| Les | Symptoom | Preventie |
|-----|----------|-----------|
| `from __future__ import annotations` in endpoint files | `PydanticUserError: TypeAdapter is not fully defined` bij `Query(...)` annotations | Pre-commit check: verbied deze import in `src/core/api/**` |
| `@asynccontextmanager` decorated functie als `Depends()` | 500 error: `_AsyncGeneratorContextManager` not async iterator | AST-based pre-commit hook detecteert dit patroon |
| Graceful degradation voor optionele services | 500 bij ontbrekende ActivePieces credentials | `_DisabledServiceClient` stub pattern; vangt config errors in `__init__` |
| `cast()` naar Pydantic model na session close | `MissingGreenlet` bij `from_attributes=True` | `model_validate()` binnen sessie, of `expunge()` in repository |

### 10.4 Security & Governance

| Les | Impact | Fix |
|-----|--------|-----|
| `tenant_id` uit request body / WS payload | Cross-tenant spoofing | Altijd uit JWT claim / ContextVar; nooit uit client payload |
| Fail-open adapters (`return True` op exception) | Security bypass bij service failure | Fail-closed (`return False`) + logging + metric |
| Placeholder secrets in `.env.example` | Productie startup met default secrets | `ConfigValidator` blokkeert startup bij bekende placeholders; CI check op sync |
| Egress control niet gewired aan HTTP clients | Outbound calls zonder URL validatie | `EgressAwareAsyncClient` wrapper; feature-flag voor veilige rollout |

### 10.5 Test Stabiliteit

| Les | Metric Before | Metric After |
|-----|--------------|--------------|
| `importlib.reload()` verbod | 231 failures | 0 failures |
| Redis socket timeouts | 3+ uur hangs | 2s timeout, fast fail |
| Streaming test runner | Summary lost bij timeout | Guaranteed summary capture |
| Function-scope fixtures | State pollution | Clean state per test |

### 10.6 Council & AI Act Governance

| Les | Context | Toepassing |
|-----|---------|------------|
| `require_council_approval()` helper | 6 audit gaps gefixt met 5 regels per route | Nieuwe AI-routes: altijd deze helper gebruiken; geen legacy `OversightGate` |
| Cache invalidatie triggers | RBAC/toolbroker/policy wijzigingen → stale officer cache | Event-bus listeners voor auto-flush; manual `invalidate_tenant()` bij ad-hoc changes |
| Hash chain breaks = compliance incident | `copilot_hash_chain_breaks_total` moet altijd 0 zijn | Monitoren + runbook `council-hash-chain-break.md` |
| Deliberation P95 SLA < 500ms | Cache hit rate doel >= 70% | Cache fingerprint review bij < 70% hit rate |

---

*Eigenaar: Rakesh Ramkhelawan | Laatste update: 2026-05-27 (review + fixes door Claude)*
*Wijzigingen aan dit document vereisen expliciete toestemming van de eigenaar.*
