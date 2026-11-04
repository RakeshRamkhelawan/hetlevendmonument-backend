# ADR-032: Frontend Pagina-Architectuur & Volledige Scope Definitie

## Status

Accepted — 2026-05-28 | Author: Rakesh Ramkhelawan

---

## Context

Tussen april en mei 2026 zijn alle frontend-pagina's van het SanskritiSetu-platform systematisch
in scope-documenten vastgelegd (`docs/frontend/pages/`). Elk document beschrijft routes, layout,
component-breakdown, API-koppelingen, rechtenmatrix en open punten. ADR-028 regelt de visuele
redesign en het design system; dit ADR-032 is de **architecturele consolidatie** van alles wat
over de applicatie als geheel is besloten: welke pagina's bestaan, hoe ze navigeren, welke
patronen overal gelden, en welke architecturele keuzes niet pagina-specifiek maar
applicatie-breed zijn.

### Aanleiding

- Het platform heeft 1.043 TypeScript/TSX-bestanden. Zonder expliciete scope-definitie per
  pagina ontstond dubbele implementatie, ontbrekende auth-guards en inconsistente API-patronen.
- De Domain Packs P0-audit (mei 2026) toonde aan dat drie kritieke bugs waren ingeslopen door
  het ontbreken van een canonical scope: een floating `get_db` die RLS omzeilde, `tenant_id`
  als `UUID` terwijl het model `Integer` gebruikt, en een route die `/stats` als UUID parseerde.
- Diepgaande audit (2026-05-28) heeft aangetoond dat CVA, Copilot, Focus Builder en CRAG
  **niet functioneren** vanwege zes structurele root causes (zie sectie 10).

---

## Decision

### 1. Volledige Pagina-Inventaris

Elke pagina heeft een goedgekeurd scope-document. De tabel hieronder is de **enige autoriteit**
over wat er bestaat en wat elke pagina doet. Afwijkingen van de scope-documenten vereisen een
update van het betreffende document vóór implementatie.

| # | Pagina | Route | Scope-document | Toegang |
|---|--------|-------|----------------|---------|
| 00 | Landing page | `/` | `00-landing-page-scope.md` | Publiek |
| 01 | Login | `/login` | `01-login-scope.md` | Publiek |
| 02 | Register | `/register` | `02-register-scope.md` | Publiek |
| 03 | Demo | `/demo` | `03-demo-scope.md` | Publiek |
| 04 | Onboarding Wizard | `/onboarding` | `04-onboarding-wizard-scope.md` | Nieuw ingelogd |
| 05 | Dashboard | `/dashboard` | `05-dashboard-scope.md` | Auth |
| 06 | Automatiseringen | `/automatiseringen` | `06-automatiseringen-scope.md` | Auth |
| 07 | Agents | `/agents` | `07-agents-scope.md` | Auth |
| 08 | Compliance | `/compliance` | `08-compliance-scope.md` | Auth |
| 09 | Instellingen | `/instellingen` | `09-instellingen-scope.md` | Auth |
| 09b | Instellingen Organisatie | `/instellingen/organisatie` | `09b-instellingen-organisatie-scope.md` | Tenant-admin |
| 10 | Admin | `/admin` | `10-admin-scope.md` | Platform-admin |
| 11 | Ontwikkelaar | `/developer` | `11-ontwikkelaar-scope.md` | Auth + dev_mode |
| 12 | Copilot Panel | Sliding overlay | `12-copilot-panel-scope.md` | Auth |
| 13 | Kennis | `/kennis` | `13-kennis-scope.md` | Auth |
| 14 | Planning | `/planning` | `14-planning-scope.md` | Auth |
| 15 | Sandbox | `/sandbox` | `15-sandbox-scope.md` | Auth |
| 16 | AI Council | `/council` | `16-ai-council-scope.md` | Auth |
| 17 | Personas | `/instellingen/personas` | `17-personas-scope.md` | Tenant-admin |
| 18 | Domain Packs | `/instellingen/domain-packs` | `18-domain-packs-scope.md` | Auth (activeren: tenant-admin) |
| 19 | HITL | `/hitl` | `19-hitl-scope.md` | Auth |
| 20 | Analytics | `/analytics` | `20-analytics-scope.md` | Auth (volledig: tenant-admin) |
| 21 | Digital Twin | `/instellingen/digital-twin` | `21-digitaltwin-scope.md` | Auth (eigen profiel) |
| 22 | Platform P0-blockers | N/v.t. (cross-cutting) | `22-platform-p0-blockers-scope.md` | Intern referentiedoc |
| 23 | Prana Dashboard | `/prana` | (nieuw -- SP-FE-2F) | Auth + `prana:read` |
| 24 | A2A Contracts | `/prana/contracts` | (nieuw -- SP-FE-2F) | Auth + `prana:read` |
| 25 | Shadow CEO Monitor | `/shadow-ceo` | (nieuw -- SP-FE-2F) | Auth + `governance:read` |
| 26 | Tool Broker Registry | `/tools` | (nieuw -- SP-FE-2E) | Auth + `agents:manage` |
| 27 | Tool Audit Logs | `/tool-audit-logs` | (nieuw -- SP-FE-2E) | Auth |
| 28 | Digital Twin (top-level) | `/digital-twin` | (nieuw -- SP-FE-2G, vervangt `/instellingen/digital-twin`) | Auth + `twin:read` |
| 29 | Trace Viewer | `/traces` | (nieuw -- SP-FE-2G) | Auth + `trace:read` |

**Totaal: 29 app-pagina's + 1 intern referentiedocument** (inclusief 2 publieke, 3 sub-instellingen, 1 overlay).

**Noot (2026-06-29):** `/digital-twin` is verplaatst van `/instellingen/digital-twin` naar een top-level route (pagina #28). De old route was alleen beschreven in ADR-032 §1 en nooit in productie; de nieuwe top-level route is gewired in SP-FE-2G Dag 3.

Toekomstige pagina's krijgen een volgnummer (22+) en een goedgekeurd scope-document vóór
implementatie begint.

---

### 2. Navigatiestructuur

#### Primaire sidebar (geauthenticeerde gebruikers, 15 items na SP-FE-2G)

```
Dashboard                (/dashboard)
Automatiseringen         (/automatiseringen)
Agents                   (/agents)
Kennis                   (/kennis)
Planning                 (/planning)
AI Council               (/council)
HITL                     (/hitl)
Tool Broker              (/tools)          [SP-FE-2E]
Audit Logs               (/tool-audit-logs) [SP-FE-2E]
Compliance               (/compliance)
Prana                    (/prana)          [SP-FE-2F]
A2A Contracts            (/prana/contracts) [SP-FE-2F]
Shadow CEO               (/shadow-ceo)     [SP-FE-2F]
Digital Twin             (/digital-twin)   [SP-FE-2G]
Developer                (/developer)      [dev_mode only]
```

#### Instellingen (genest)

```
/instellingen
  ├── Profiel             (eigen account)
  ├── Organisatie         (/instellingen/organisatie)
  ├── Personas            (/instellingen/personas)
  ├── Domain Packs        (/instellingen/domain-packs)
  └── Digital Twin        (/instellingen/digital-twin)
```

#### Platform-admin (apart portaal)

```
/admin
  ├── Tenants
  ├── Domain Packs catalogus
  ├── Gebruikers
  └── Platform analytics
```

#### Vaste UI-elementen

- **Topbalk**: logo, actieve pagina-naam, notificatie-badge (HITL + proactieve meldingen),
  gebruikersmenu (avatar → logout/profiel), Co-pilot open-knop
- **Co-pilot panel**: sliding overlay (rechts), beschikbaar op elke pagina,
  triggered via topbalk-knop of keyboard shortcut
- **Toast-melding**: globaal, linksonder, max 3 tegelijk zichtbaar

---

### 3. Routestructuur in App.tsx

#### Publieke routes (geen auth vereist)

```
/                     → Landing
/login                → Login
/register             → Register
/demo                 → Demo (rate-limited, geen account nodig)
```

#### Auth-protected routes (JWT vereist)

```
/onboarding           → OnboardingWizard (redirect na eerste login)
/dashboard            → Dashboard
/automatiseringen     → Automatiseringen
/agents               → Agents
/kennis               → Kennis
/planning             → Planning
/council              → AICouncil
/hitl                 → HITLQueue redesign (lazy) -- was HITLPage (SP-FE-2E)
/analytics            → Analytics (lazy)
/sandbox              → Sandbox
/compliance           → Compliance
/developer            → Developer (dev_mode guard)

/instellingen         → Instellingen (layout wrapper)
  /profiel            → ProfielInstellingen
  /organisatie        → OrganisatieInstellingen
  /personas           → Personas (tenant-admin guard)
  /domain-packs       → DomainPacks (tenant-admin guard voor mutaties)

-- Toegevoegd SP-FE-2E (2026-06-28):
/tools                → ToolBrokerRegistry (lazy, PermissionGate agents:manage)
/tool-audit-logs      → ToolAuditLogs (lazy)

-- Toegevoegd SP-FE-2F (2026-06-28/29):
/prana                → PranaDashboard (lazy, PermissionGate prana:read)
/prana/contracts      → A2AContracts (lazy, PermissionGate prana:read)
/shadow-ceo           → ShadowCEOMonitor (lazy, PermissionGate governance:read)

-- Toegevoegd SP-FE-2G (2026-06-29):
/digital-twin         → DigitalTwin (lazy, PermissionGate twin:read)
/traces               → TraceViewerPage (lazy, PermissionGate trace:read)
```

#### Admin-only routes

```
/admin/*              → AdminPortaal (platform-admin guard)
```

#### Fallback

```
*                     → 404-pagina (inline component, geen eigen route)
```

**Loading strategie**: dashboard, agents, hitl, kennis, planning, council — **eager** (kritisch
pad, altijd nodig). analytics, digital-twin, sandbox, admin — **lazy** (minder frequent,
chunked).

---

### 4. Applicatie-brede Technische Besluiten

#### 4.1 LLM-provider strategie: LLM-agnostisch

**Besluit (2026-05-28):** Het platform is en blijft volledig LLM-agnostisch. De keuze welke
providers in productie worden aangeboden is een go-live beslissing van Rakesh. Huidige
werkproviders voor development zijn **Google Gemini** en **DeepSeek**. Anthropic kan later
worden toegevoegd maar is geen vereiste.

Prioriteit op dit moment: alle bestaande LLM-features (CVA, Copilot, Focus Builder, CRAG)
aantoonbaar laten werken met de huidige provider-configuratie. Geen provider-migratie.

**Abonnement-prijzen** zijn berekend op basis van Anthropic-tarieven als referentie. Dat is
uitsluitend een commerciële keuze en impliceert niet dat Anthropic als provider wordt ingezet.

**Provider-abstractie (bestaand patroon via FailoverLLMProvider, ADR-026):**

```text
Elke LLM-aanroep gaat via de provider-abstractielaag.
Provider-keuze is configuratie (env vars), niet hardcoded in features.
```

Concrete aandachtspunten (functioneel, niet provider-specifiek):

| Component | Bekende status | Prioriteit |
| --- | --- | --- |
| CVA (`/api/v1/copilot/turn`) | Werkt niet | P0 |
| Copilot WebSocket chat | Werkt niet | P0 |
| Focus Builder workflow-generatie | Werkt niet | P0 |
| CRAG (Corrective RAG) | Werkt niet | P0 |
| Conversatie-samenvatting bij > 10 berichten | Ontbreekt | P1 |

#### 4.2 Server-state: TanStack Query (React Query)

Alle API-data via React Query. Geen directe `useEffect + fetch` combinaties.

Naamgevingsconventie voor query keys:

```typescript
// Factory pattern — verplicht voor alle nieuwe queries
const queryKeys = {
  list: (filters?: Filters) => ['resource', 'list', filters] as const,
  detail: (id: string) => ['resource', 'detail', id] as const,
};
```

Cache-invalidatie na mutaties altijd via `queryClient.invalidateQueries({ queryKey: [...] })`.
Geen handmatige `refetch()` calls tenzij onvermijdelijk.

#### 4.3 Client-state: Zustand

Per feature-domein een eigen store. Stores zijn nooit globaal shared zonder expliciete noodzaak.
Devtools plugin altijd enabled in development.

Bestaande stores (niet dupliceren):
- `useDigitalTwinStore` — twin-profiel + consent + erasure state
- `useAuthStore` — JWT-claims, permissions, roles
- `useAgenticDashboardStore` — dashboard-specifieke UI-staat

#### 4.4 Authenticatie & tenant-isolatie in de frontend

- **Tokens**: httpOnly cookie (access_token + refresh_token). Nooit in localStorage.
- **tenant_id**: altijd gelezen uit JWT-claims via `useAuthStore`. Nooit uit URL-params of
  request-body gestuurd.
- **tenant_id type**: altijd `number` (int) — nooit `string | UUID`. De backend slaat het op
  als `Integer`; verkeerde types veroorzaken runtime-500s.
- **Guards**: `PermissionGate` component (scope-based) en `ClassificationWrapper` (data
  classification level) zijn de enige twee auth-UI-primitieven.

#### 4.5 WebSocket-patroon

Alle WebSocket hooks volgen het `mountedRef`-patroon:

```typescript
const mountedRef = useRef(false);

useEffect(() => {
  mountedRef.current = true;
  connect();
  return () => {
    mountedRef.current = false;
    wsRef.current?.close();
    wsRef.current = null;
  };
}, [connect]);
```

Token-overdracht: cookie-first (browser stuurt `access_token` cookie automatisch bij WS
handshake). Fallback: `?token=<jwt>` query-parameter — uitsluitend voor WebSocket, nooit voor
HTTP endpoints.

#### 4.6 Paginering op alle list-endpoints

Elk list-component gebruikt `limit` + `offset` parameters. Standaardwaarden:
- `limit`: 50 (max 1000)
- `offset`: 0

Paginering-state wordt bewaard in URL-querystring zodat deep-links werken.

#### 4.7 Error boundaries

Elke route-level component heeft een error boundary. Foutpagina toont:
- Generieke boodschap (nooit stack trace in productie)
- Knop "Probeer opnieuw" (roept `reset()` aan)
- Link naar `/dashboard`

Geen blootstelling van interne paden, API-responses of JWT-claims aan de gebruiker via
foutmeldingen.

#### 4.8 Datum/tijd

Alle datums worden opgeslagen en ontvangen als ISO 8601 UTC string. Weergave converteert
naar lokale tijd van de gebruiker via `Intl.DateTimeFormat`. Geen `moment.js` — gebruik
native `Intl` of `date-fns`.

---

### 5. Domain Packs P0-fixes (vastgelegd als precedent)

Tijdens de scope-definitie (2026-05-28) zijn vijf pre-existing bugs gevonden en opgelost in de
Domain Packs implementatie. Ze zijn hier gedocumenteerd als architectuurpatroon-precedent — elk
is een voorbeeld van een klasse van fouten die applicatie-breed kan optreden.

#### Bug C-1: Lokale `get_db` omzeilt RLS

**Gevonden in:** `src/core/api/domain_packs.py` (originele implementatie)

**Probleem:** De router definieerde zijn eigen `get_db` wrapper die
`db_manager.get_async_session()` aanriep. Die wrapper injecteerde géén
`SET LOCAL app.current_tenant = '{tenant_id}'`, waardoor RLS (ADR-005) werd omzeild.

**Fix:** Alle routers importeren exclusief de canonical `get_db` uit
`src.core.database.database`. Nooit een lokale wrapper aanmaken.

**Regel:** `from src.core.database.database import get_db` — dit is de enige geldige
importlocatie. Elke afwijking is een security-bug.

#### Bug C-2: Route-shadowing (FastAPI greedy path matching)

**Gevonden in:** `src/core/api/domain_packs.py`

**Probleem:** `GET /{pack_id}` stond boven `GET /stats` in de router-definitie. FastAPI
probeerde "stats" te parsen als UUID-parameter → 422 Unprocessable Entity. De stats-endpoint
was effectief onbereikbaar.

**Fix:** Vaste padsegmenten (`/stats`, `/health`, `/archive`) altijd declareren vóór
parameterroutes (`/{resource_id}`).

**Regel voor alle routers:**
```python
# GOED: specifieke paden voor wildcards
@router.get("/stats")
@router.get("/health")
@router.get("/{resource_id}")   # onderaan
```

#### Bug C-3: `tenant_id` type mismatch (UUID vs. int)

**Gevonden in:** `domain_pack_repository.py`, `schemas.py`, `evaluation_repository.py`

**Probleem:** Drie lagen declareerden `tenant_id: UUID` terwijl het DB-model `Integer` gebruikt.
SQLAlchemy genereerde bij uitvoering een type-fout.

**Fix:** `tenant_id` is altijd `int` in alle lagen: repository, schema, Pydantic-model,
endpoint-signature.

**Regel:** De DB is leidend. Bij twijfel: kijk naar het SQLAlchemy-model. `Integer` in het
model = `int` in alle Python-lagen.

#### Bug C-4: Pack Selector bevroeg geen database

**Gevonden in:** `src/core/api/v1/company/pack_selector_router.py`

**Probleem:** `score_all_packs([], signals, ...)` scoorde altijd een lege lijst omdat
`_execute_pack_selection()` geen packs uit de DB haalde. De scorer retourneerde altijd `[]`.

**Fix:** DB-query toegevoegd vóór de scorer-aanroep:
```python
stmt = select(DomainPack).where(
    DomainPack.tenant_id == tenant_id,
    DomainPack.status == "active",
)
```
Mapper naar scorer-interface via `SimpleNamespace` (geen modelwijziging vereist).

#### Bug C-5: Verkeerde `get_current_tenant_id` genereerde willekeurige UUID per request

**Probleem:** De originele implementatie riep `get_current_tenant_id()` aan die een nieuwe
`uuid4()` genereerde bij elke aanroep. Elk request zag willekeurige tenant-data.

**Fix:** Vervangen door `get_current_user` dependency + `current_user.tenant_id` (int uit JWT).

**Regel:** `tenant_id` in endpoints altijd via `current_user: UserResponse = Depends(get_current_user)`,
dan `current_user.tenant_id`. Nooit via een afzonderlijke `get_tenant_id()` helper die de
JWT niet leest.

---

### 6. Router-registratie canoniek patroon

Alle routers worden geregistreerd via `src/core/api/router_registry.py`. Directe registratie
in `main.py` of elders is verboden.

Verplicht patroon bij elke nieuwe router:

```python
def _register_mijn_domein(app: FastAPI) -> int:
    count = 0
    try:
        from src.core.api.mijn_domein import router as mijn_router
        app.include_router(mijn_router, tags=["Mijn Domein"])
        count += 1
        logger.debug("Mijn Domein router registered")
    except Exception as e:
        logger.warning("Skipping Mijn Domein router: %s", e)
    return count
```

`try/except` is verplicht om te voorkomen dat één ontbrekende import de volledige
applicatiestart blokkeert. De warning in de log maakt het onderscheid zichtbaar.

---

### 7. Backend-API prefix-conventie

| Type | Prefix | Voorbeeld |
|------|--------|-----------|
| Versioned REST | `/api/v1/` | `/api/v1/domain-packs` |
| Analytics (legacy) | `/api/analytics/` | `/api/analytics/events` |
| Admin | `/api/v1/admin/` | `/api/v1/admin/digital-twin/stats` |
| Public (Foundation Portal) | `/api/v1/public/{slug}/` | `/api/v1/public/ketikoti/content` |
| WebSocket | `/ws/` | `/ws/hitl/{tenant_id}` |

Geen afwijkingen van deze conventies zonder ADR-update.

---

### 8. Scope-document lifecycle

Een scope-document (`docs/frontend/pages/NN-naam-scope.md`) volgt deze lifecycle:

1. **Draft** — aangemaakt op basis van bestaande code + backend-inventarisatie
2. **Goedgekeurd** — gebruiker heeft het document gereviewed en expliciet goedgekeurd
3. **Implementatie** — frontend wordt gebouwd conform het document
4. **Sloten** — implementatie gereed, doc bijgewerkt met eindstatus

Pagina-implementatie **mag niet beginnen** zonder status "Goedgekeurd".
Scope-wijzigingen tijdens implementatie worden teruggevoerd naar het document; het document
is altijd de meest recente bron van waarheid, niet de code.

Huidige status per document:

| Document | Status |
|----------|--------|
| 00 t/m 17 | Goedgekeurd |
| 18-domain-packs-scope.md | Goedgekeurd (2026-05-28) |
| 19-hitl-scope.md | Goedgekeurd (2026-05-28) |
| 20-analytics-scope.md | Goedgekeurd (2026-05-28) |
| 21-digitaltwin-scope.md | Goedgekeurd (2026-05-28) |
| 22-platform-p0-blockers-scope.md | Goedgekeurd (2026-05-28) |

---

### 10. LLM-feature Audit Bevindingen (2026-05-28)

Op 2026-05-28 is een diepgaande audit uitgevoerd van de vier LLM-features die niet functioneren:
CVA, Copilot WebSocket, Focus Builder en CRAG. De volledige bevindingen inclusief fix-plan en
prioriteitsvolgorde staan in `docs/frontend/pages/22-platform-p0-blockers-scope.md`.

Hieronder de architectureel relevante bevindingen die in toekomstige implementaties voorkomen
moeten worden.

#### RC-1: `complete_json()` ontbreekt in alle actieve providers

De `CopilotLLMHandler` vereist `complete_json()`. **Uitsluitend** `AnthropicClient` implementeert
deze methode. `DeepSeekClient`, `GoogleClient`, `OllamaClient` en `MockProvider` gooien
`NotImplementedError`. De exception wordt generiek gevangen waardoor de gebruiker een BLOCKED-
response ziet zonder foutmelding.

**Architectuurpatroon:** Elke nieuwe LLM-provider klasse **moet** `complete_json()` implementeren
voordat hij geregistreerd wordt in `FailoverLLMProvider`. Geen provider is valide zonder deze methode.

#### RC-2: Provider SDK-versie en import-pad zijn eigendom van de abstractielaag

`gemini_provider.py` en `fallback_chain.py` gebruikten het verouderde `google.generativeai`
import-pad terwijl het geinstalleerde package `google-genai>=1.0.0` is.

**Architectuurpatroon:** SDK-imports horen uitsluitend in de provider-klasse (niet in feature-code).
Bij een SDK-upgrade moeten alle import-locaties gesynchroniseerd worden. `production_llm_client.py`
is de canonieke referentie voor correcte syntax.

#### RC-3: Maximaal een LLM-service singleton per applicatie

`llm_service.py` en `llm_config.py` bevatten elk een `get_llm_service()` factory met een eigen
singleton. Dit leidt tot ongedefinieerd gedrag bij provider-switching.

**Architectuurpatroon:** De `GuaranteedLLMService` in `llm_config.py` is de enige geldige
LLM-service singleton. `llm_service.py` wordt gedepreceerd zodra RC-3 is opgelost.

#### RC-4: Nooit een model-naam hardcoderen in feature-code

`crag_graph.py` hardcodeerde `model="gemini-1.5-flash"` op drie plaatsen, waarmee de
provider-abstractielaag (ADR-026) volledig werd omzeild.

**Architectuurpatroon:** Modelkeuze is altijd `config.LLM_MODEL` of het actieve provider-model
uit `GuaranteedLLMService`. Nooit een model-string in feature-code.

#### RC-5: Exceptions in LLM-feature-code altijd loggen, nooit swallowing

Focus Builder gebruikte `except Exception: pass` waardoor LLM-fouten onzichtbaar waren.

**Architectuurpatroon:** Zie CLAUDE.md regel 5 (nooit exceptions slikken). `best_effort` is
uitsluitend voor niet-kritieke bijwerkingen (audit logs, metrics). LLM-aanroepen zijn kritiek;
fouten moeten worden gelogd met `exc_info=True` en resulteren in een expliciete foutrespons.

#### RC-6: Dependency injection in Copilot — factory vs. client

`dependencies.py:35` injecteerde een `LLMProviderFactory` in `LLMHandler` in plaats van een
geinitaliseerde `LLMClient`. De factory heeft geen `complete_json()`.

**Architectuurpatroon:** DI-containers leveren altijd volledig geinitaliseerde clients, niet
factories. Een factory wordt nooit als handler-argument doorgegeven.

#### Platform P0-blockers (opsomming)

| Bug | Bestand | Impact |
| --- | --- | --- |
| P0-1: `tenant_id = 1` hardcoded fallback | `src/core/api/auth/router.py:162` | Alle multi-tenancy geblokkeerd |
| P0-3: RAG-stubs retourneren nep-data | `src/core/api/rag_endpoints.py:270` | Gebruikers zien nepresultaten |
| P0-4: `_execute_step()` actieve stub | `src/domains/workflows/services.py:71` | Workflow-automatisering werkt niet |
| P0-5: `ExportJob` model/tabel ontbreekt | `src/core/models/gdpr_models.py` | GDPR Art. 20 geblokkeerd |
| P0-8: Secret key fallback naar bekende string | `production_config.py:22`, `interfaces.py:393` | JWT-forgery mogelijk |
| P0-9: SQLite als database default | `src/core/shared/config.py:56` | RLS volledig uitgeschakeld |
| P0-10: Document/production stubs retourneren 200 | `document_endpoints.py`, `production_endpoints.py` | Silent data loss |

#### RC-7/RC-8: Configuratie-defaults als security-pattern

Naast de zes eerder genoemde RC-patronen zijn twee nieuwe architecturele anti-patterns
ontdekt (Fase 2, 2026-05-28):

**P0-8 patroon — Nooit een bekende string als fallback voor cryptografische sleutels:**

```python
# FOUT — bij ontbrekende env var tekent de app JWTs met publiek bekende string
secret_key = os.getenv("SECRET_KEY") or "dev-secret-change-in-production"

# GOED — fail-secure: geen env var = geen start
secret_key = os.getenv("SECRET_KEY")
if not secret_key or secret_key in KNOWN_INSECURE_DEFAULTS:
    raise ConfigurationError("SECRET_KEY is missing or insecure")
```

**P0-9 patroon — SQLite is verboden; PostgreSQL is niet-onderhandelbaar:**

```python
# FOUT — SQLite default schakelt RLS (ADR-005) volledig uit
database_url: str = Field(default="sqlite:///./sanskriti_setu.db")

# GOED — geen default; ontbrekende URL = geen start
database_url: str = Field(default="")
# + Pydantic validator die "sqlite" afwijst met ValueError
```

Volledige fix-plan (7 werkdagen, 23-30u) inclusief Definition of Done per P0: zie
`docs/frontend/pages/22-platform-p0-blockers-scope.md`.

#### Ground-truth scan bevindingen (Fase 3, 2026-05-28)

Een systematische grep-scan van alle ~1.900 Python-bestanden en 1.043 TypeScript-bestanden
(niet documentatie-gedreven, maar code-gedreven) bracht de volgende additionele
architecturele anti-patterns aan het licht.

**Totaalscore:**

- Backend: ~55-60% productierijp
- Frontend: ~65-70% gebruikt echte API-calls
- 14 Python-bestanden met expliciete STUB-markers actief in productie
- 14 endpoints die nep-data retourneren, geregistreerd via `router_registry.py`
- 11 TypeScript-componenten met volledig hardcoded mock-data

##### Architectuurpatroon GS-A: Nooit een governance-agent met mock execution paths in productie

`src/core/agents/ethics_agent.py` heeft GEEN niet-mock code-pad. Alle vier execution
branches (`_mock_risk_assessment`, `_mock_ethical_review`, etc.) retourneren
`"mock_analysis": True`. Een governance agent die altijd nep-analyses produceert
ondermijnt het volledige Council-systeem (ADR-027).

Regel: een agent met een `_mock_*` prefix in zijn execution path mag NOOIT als
Council Officer worden geregistreerd. Band-aid voor launch: raise
`NotImplementedError`. Echte implementatie: LLM-gestuurde analyse met gestructureerde
respons (`risk_flags`, `ethics_score`, `recommendation`).

##### Architectuurpatroon GS-B: Stub-modules zijn NOOIT geregistreerde productie-endpoints

Drie modules (`collaboration_endpoints.py`, `phase2_endpoints.py`,
`autonomous_endpoints.py`) zijn als stub gemarkeerd maar actief geregistreerd via
`router_registry.py`. Ze retourneren HTTP 200 met `"status": "stub_implementation"`.

Regel: een bestand met `# STUB` header of `"stub_implementation"` response mag NOOIT
via `router_registry.py` worden geregistreerd als productie-endpoint. Gebruik HTTP 501
als tijdelijke placeholder.

##### Architectuurpatroon GS-C: AI Act compliance-endpoints mogen nooit gefaked zijn

`useExplainability.ts` heeft de echte API-call uitgecommentarieerd en vervangt hem door
`setTimeout(resolve, 500) + generateMockExplainability()`. Dit maakt AI Act Art. 13
(right-to-explanation) structureel niet-aantoonbaar.

Regel: hooks die compliance-data ophalen (`useExplainability`, `useAgentSuggestions`,
Council-gerelateerde hooks) mogen NOOIT een `mockMode = true` default of gesimuleerde
netwerkvertraging bevatten. Mocks zijn uitsluitend toegestaan in testbestanden
(`*.test.ts`, `*.spec.ts`).

##### Architectuurpatroon GS-D: Math.random() is verboden in UI die financiele of risicodata toont

`MissionProposalModal.tsx` gebruikt `Math.random()` voor kostenscatting en risicoscore.
`MetricsCharts.tsx` voegt `(0.9 + Math.random() * 0.2)` variantie toe aan API-data.

Regel: `Math.random()` is verboden in componenten die data tonen die als basis voor
beslissingen dient. Als de backend de waarde nog niet levert: toon `"--"` of
`"onbekend"`. Nooit een willekeurig getal presenteren als betrouwbare informatie.

Alle nieuw ontdekte bevindingen (GS-1 t/m GS-FE-6) zijn gedocumenteerd in
`docs/frontend/pages/22-platform-p0-blockers-scope.md` (Deel 2d).
Bug GS-1 (ethics agent) is vastgelegd in ADR-027; bug GS-FE-1 (useExplainability)
is vastgelegd in ADR-031.

---

### 9. Openstaande architectuurkeuzes (te beslissen voor implementatiestart)

| Vraagstuk | Opties | Huidige voorkeur |
|-----------|--------|-----------------|
| Routing library | React Router v6 (huidig) vs. TanStack Router | React Router v6 (bestaande codebase) |
| Formulier-bibliotheek | React Hook Form + Zod (al gebruikt) vs. Conform | React Hook Form + Zod |
| Grafiekbibliotheek | Recharts (gebruikt) + SVG (MetricsCharts) | Recharts voor data, SVG voor eenvoudige meters |
| Internationalisation | i18next (al aanwezig) vs. geen | i18next (NL primair, EN secundair) |
| Feature flags frontend | Via JWT-claims + PermissionGate | JWT-claims (geen aparte client-side FF library) |

---

## Consequences

### Positief

- Elke nieuwe ontwikkelaar (of AI-agent) heeft één document dat de volledige scope van de
  applicatie vastlegt. Geen discovery-werk meer nodig voor bestaande pagina's.
- De vijf Domain Packs P0-bugs zijn gedocumenteerd als patronen; toekomstige code-reviews
  checken expliciet op deze anti-patterns.
- LLM-feature audit (sectie 10) documenteert zes root causes en een geconsolideerde
  prioriteitsvolgorde; toekomstige sessies kunnen direct starten zonder discovery-werk.
- Route-shadowing bug-klasse is nu canoniek gedocumenteerd; FastAPI-routers worden
  standaard gecontroleerd op vaste-voor-wildcard volgorde.

### Negatief

- 22 pagina's is een grote scope voor een solo-developer. Implementatie vereist prioritering
  per sprint; niet alles kan tegelijk worden gebouwd.
- Zes LLM-root causes (CVA, Copilot, Focus Builder, CRAG) moeten vóór productielancering
  worden opgelost. Prioriteitsvolgorde en tijdsinschatting: zie sectie 10 en scope doc 22.
- Scope-documenten moeten worden bijgehouden bij elke architectuurwijziging. Als de code
  een document overleeft zonder update, verliest het document zijn autoriteit.
- Sommige pagina's (Sandbox, Collaboration Canvas, Prana Economy) zijn nog niet als scope-
  document gedefineerd. Die pagina's mogen niet worden geïmplementeerd tot dat gebeurd is.

### Geraakte ADRs

| ADR | Relatie |
|-----|---------|
| ADR-003 | tenant_id altijd uit JWT-claim (C-5 fix) |
| ADR-004 | ORM hook vereist canonical get_db (C-1 fix) |
| ADR-005 | RLS werkt alleen met canonical get_db |
| ADR-028 | Design system, visuele besluiten — dit ADR voegt scope toe, vervangt niet |
| ADR-031 | AI Act compliance vereist tenant_id als int, niet UUID, voor governance-routes |

---

## Referenties

Alle pagina-scope-documenten zijn beschikbaar in `docs/frontend/pages/`:

- [00-landing-page-scope.md](../frontend/pages/00-landing-page-scope.md)
- [01-login-scope.md](../frontend/pages/01-login-scope.md)
- [02-register-scope.md](../frontend/pages/02-register-scope.md)
- [03-demo-scope.md](../frontend/pages/03-demo-scope.md)
- [04-onboarding-wizard-scope.md](../frontend/pages/04-onboarding-wizard-scope.md)
- [05-dashboard-scope.md](../frontend/pages/05-dashboard-scope.md)
- [06-automatiseringen-scope.md](../frontend/pages/06-automatiseringen-scope.md)
- [07-agents-scope.md](../frontend/pages/07-agents-scope.md)
- [08-compliance-scope.md](../frontend/pages/08-compliance-scope.md)
- [09-instellingen-scope.md](../frontend/pages/09-instellingen-scope.md)
- [09b-instellingen-organisatie-scope.md](../frontend/pages/09b-instellingen-organisatie-scope.md)
- [10-admin-scope.md](../frontend/pages/10-admin-scope.md)
- [11-ontwikkelaar-scope.md](../frontend/pages/11-ontwikkelaar-scope.md)
- [12-copilot-panel-scope.md](../frontend/pages/12-copilot-panel-scope.md)
- [13-kennis-scope.md](../frontend/pages/13-kennis-scope.md)
- [14-planning-scope.md](../frontend/pages/14-planning-scope.md)
- [15-sandbox-scope.md](../frontend/pages/15-sandbox-scope.md)
- [16-ai-council-scope.md](../frontend/pages/16-ai-council-scope.md)
- [17-personas-scope.md](../frontend/pages/17-personas-scope.md)
- [18-domain-packs-scope.md](../frontend/pages/18-domain-packs-scope.md)
- [19-hitl-scope.md](../frontend/pages/19-hitl-scope.md)
- [20-analytics-scope.md](../frontend/pages/20-analytics-scope.md)
- [21-digitaltwin-scope.md](../frontend/pages/21-digitaltwin-scope.md)
- [22-platform-p0-blockers-scope.md](../frontend/pages/22-platform-p0-blockers-scope.md)

---

## Implementatie-bevindingen -- Architectuur Audit 2026-05-31

### WE-010 [HIGH] Canvas REST URL: /canvases (meervoud) vs /canvas (enkelvoud)

**Situatie:** Frontend roept canvas REST endpoints aan.
**Werkelijkheid:** Backend Canvas router heeft `APIRouter(prefix='/canvas')` geregistreerd
op `/api/v1` -- volledig pad: `/api/v1/canvas` (enkelvoud).
Frontend roept `/api/v1/canvases` (meervoud) aan via `wave-b-paths.ts`.
Alle canvas REST-aanroepen retourneren 404.
**Bewijs:** `frontend/src/lib/api/wave-b-paths.ts`: `canvases: '/api/v1/canvases'`.
`src/core/api/v1/canvas/router.py:36`: `prefix='/canvas'`.
`router_registry.py:255`: `prefix='/api/v1'`.
**Fix:** `WAVE_B_PATHS.canvases` aanpassen naar `/api/v1/canvas`,
OF backend prefix wijzigen naar `/canvases` (breaking change).
**Sprint:** SP-WE-09

### WE-011 [HIGH] Analytics endpoint: /metrics vs /ooda

**Situatie:** Frontend `AnalyticsService` roept agent metrics op via `/metrics`.
**Werkelijkheid:** Backend analytics router heeft `@router.get('/agents/{agent_id}/ooda')`.
Frontend roept `/api/v1/analytics/agents/${agentId}/metrics` aan.
Alle analytics agent-metrics aanroepen retourneren 404.
**Bewijs:** `frontend/src/services/analytics/AnalyticsService.ts:68-69`,
`src/core/api/v1/analytics.py:79`.
**Fix:** Frontend pad aanpassen naar `/api/v1/analytics/agents/{id}/ooda`,
of backend alias toevoegen voor `/metrics`.
**Sprint:** SP-WE-09

### WE-019 [MEDIUM] useExplainability roept niet-bestaand missions/steps/explainability endpoint aan

**Situatie:** `useExplainability` hook haalt stap-niveau explainability op per mission-step.
**Werkelijkheid:** Geen backend endpoint bestaat voor
`/api/v1/missions/{id}/steps/{stepId}/explainability`.
Mission endpoints bestaan maar bevatten geen `/steps/{id}/explainability` subroute.
**Bewijs:** `frontend/src/lib/hooks/useExplainability.ts` (roept het pad aan),
grep op alle mission routers: geen explainability subroute geregistreerd.
**Impact:** Explainability UI retourneert altijd 404. AI Act Art. 13 right-to-explanation
is niet bereikbaar via deze hook.
**Sprint:** SP-WE-09 (stub endpoint 501) of SP-C02-B (echte implementatie)

---

## Changelog

- **2026-05-31 v1.3** -- WE-010/011/019 gedocumenteerd: canvas URL mismatch (/canvases
  vs /canvas), analytics URL mismatch (/metrics vs /ooda), useExplainability endpoint
  bestaat niet. Fix in SP-WE-09.
- **2026-05-28 v1.2** — Sectie 10 uitgebreid met ground-truth scan bevindingen (Fase 3):
  4 nieuwe architectuurpatronen GS-A/B/C/D (ethics agent mocks, stub endpoints, AI Act
  compliance hooks, Math.random in UI). P0-8/P0-9 bestanden-tabellen uitgebreid met
  derde locaties (`jwt_handler.py:102`, `container.py:86`). ADR-027 en ADR-031
  bijgewerkt met respectievelijk GS-1 en GS-FE-1 bugrapportages.
- **2026-05-28 v1.1** — Sectie 10 toegevoegd: LLM-feature audit bevindingen (RC-1 t/m RC-6,
  platform P0-blockers P0-1/P0-3/P0-4/P0-5). Context en Consequences bijgewerkt: stale
  Anthropic-only referenties vervangen door LLM-agnostische formulering. Scope doc 22
  (platform P0-blockers) toegevoegd aan referenties.
- **2026-05-28 v1.0** — Initial Accepted. Pagina-inventaris 22 pagina's (00-21),
  navigatiestructuur, routestructuur, applicatie-brede technische besluiten,
  Domain Packs P0-fixes als architectuurpatronen, router-registratie canoniek patroon,
  API-prefix conventies, scope-document lifecycle, LLM-agnostische provider-strategie.
