# ADR-035: Single-Tenant Deployment Mode

## Status

Accepted — 2026-07-02

### Status History

- 2026-06-29: Proposed — na diepgaand onderzoek + multidisciplinaire audit (77 bevindingen, 10 disciplines); AUDIT-TENANT-01 middleware reeds gesloten (commit 5c461bd7). Plan: docs/plans/AUDIT-SINGLE-TENANT-DB01-volledig-plan.md
- 2026-07-02: Accepted — alle 8 succescriteria GESLOTEN (sprints S1-S7, AUDIT-SINGLE-TENANT-DB01)

---

## Probleemstelling

SanskritiSetu is ontworpen als multi-tenant SaaS platform. Een groeiende vraag van klanten (o.a. Ketikoti Vlaardingen) is: "kunnen we dit on-premise draaien voor onze eigen organisatie?" Dat vraagt om een **single-tenant deployment mode** — één organisatie, meerdere gebruikers, geen multi-tenant JWT-claim verplicht.

Dit is fundamenteel anders dan SaaS:

| Eigenschap | SaaS (standaard) | Single-Tenant |
|---|---|---|
| Tenants | Meerdere organisaties in één DB | Één organisatie (tenant_id = 1) |
| JWT tenant claim | Verplicht | Optioneel — middleware vult aan |
| Deployment | Azure cloud | On-premise (Docker Compose) |
| Auth | JWT + tenant scope | JWT (gebruiker authenticatie), tenant automatisch |
| Config | Per-tenant | Één vaste configuratie |
| Updates | Rolling (zero-downtime) | Beheerd door klant |

---

## Context

### Huidige staat (na AUDIT-TENANT-01)

De hybride fallback-middleware is geïmplementeerd (commit 5c461bd7):

```python
# src/core/middleware/tenant_context.py — TenantMiddleware
if DEPLOYMENT_MODE == "single_tenant" and get_tenant_id() is None:
    set_tenant_id(1)   # Default tenant in single-tenant deployments
```

Dit dekt de **HTTP request lifecycle** volledig. Wat ontbreekt:

| Onderdeel | Status | Audit-bevinding |
|---|---|---|
| HTTP middleware fallback | GESLOTEN | AUDIT-TENANT-01 ✓ |
| Frontend hardcoded wss:// (5 bestanden) | OPEN | AUDIT-ST-01 |
| Docker/deployment artefacten | OPEN | AUDIT-ST-02 |
| Dramatiq worker tenant context | OPEN | AUDIT-ST-03 + **TI-004 (CRITICAL)** |
| Service-laag 13 domeinen | OPEN | AUDIT-DB-01 fase 2-4 |

### Audit-bevinding TI-004 (CRITICAL — onafhankelijk geverifieerd)

Multidisciplinaire audit 2026-06-29 bevestigde een kritieke kwetsbaarheid in de worker-lifecycle:

> `execute_workflow_step()` in `src/core/tasks/workflow_tasks.py:24` zet tenant context **alleen als** `tenant_id` aanwezig is in task_data_dict. Als het veld ontbreekt, draait de job zonder enige tenant context — dit omzeilt ADR-003/ADR-004 tenant isolatie voor alle downstream DB-operaties.

Dit is een actief risico in productie (SaaS én single-tenant) en wordt als prioriteit behandeld in deze ADR.

### Tenant isolatie is nooit een "bypass"

In single-tenant mode is `tenant_id = 1` een **echte tenant** in de database — geen fictieve waarde. De middleware-fallback vult slechts de context aan die normaal via JWT binnenkomt. Alle ADR-003/ADR-004 isolatie-mechanismen blijven actief:

- `do_orm_execute` hook filtert automatisch op `tenant_id = 1`
- `NOT NULL` constraint op alle tenant_id-kolommen
- RLS roadmap (ADR-005) werkt ongewijzigd

---

## Beslissing

### D1 — DEPLOYMENT_MODE env-var als enige schakelaar

```bash
DEPLOYMENT_MODE=saas          # standaard; multi-tenant JWT-flow actief
DEPLOYMENT_MODE=single_tenant # single-tenant; middleware fallback actief
```

Gedrag per modus:

| Gedrag | saas | single_tenant |
|---|---|---|
| JWT tenant_id claim verplicht | Ja | Nee (middleware vult aan met 1) |
| Gebruikersauthenticatie (JWT) | Ja | Ja (ongewijzigd) |
| tenant_id in DB-queries | Per JWT | Altijd 1 |
| Router/service-laag | Ongewijzigd | Ongewijzigd |
| Dramatiq workers (na D3) | tenant_id via task_data | Auto-fallback naar 1 |

**Wat NIET verandert:**
- Alle ADR-003/ADR-004/ADR-005 isolatie-invarianten
- JWT-authenticatie van gebruikers (alleen tenant scope vervalt)
- Database schema — tenant_id = 1 is gewone rij in `tenants` tabel

### D2 — Frontend WebSocket URLs dynamisch via window.location.host

Vijf productie-bestanden hebben een hardcoded `wss://api.sanskritisetu.org` fallback:

```
frontend/src/contexts/CollaborationContext.tsx:9
frontend/src/components/analytics/RealtimeDashboard.tsx:27
frontend/src/components/gen-ui/ChatInterface.tsx:44
frontend/src/components/workflow/FocusModeBuilder.tsx:145
frontend/src/hooks/usePackActivity.ts:43
```

**Beslissing:** Vervang alle vijf door het patroon dat al correct is in `useWebSocket.ts` en `useHITLWebSocket.ts`:

```typescript
const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
const host = window.location.host;
const wsUrl = import.meta.env.VITE_WS_URL || `${protocol}://${host}/ws/<pad>`;
```

`VITE_WS_URL` blijft beschikbaar als expliciete override voor atypische deployments (reverse proxy met ander host).

### D3 — Worker tenant-context decorator (adresseert TI-004 CRITICAL)

Dramatiq actors draaien buiten de ASGI request-lifecycle en krijgen geen middleware-fallback. Gecombineerd met de TI-004-kwetsbaarheid (silent skip bij missing tenant_id) is dit een actief data-integriteitsrisico.

**Beslissing:** Twee complementaire fixes:

**Fix A — TI-004: geen silent skip meer (geldt voor SaaS én single_tenant)**
```python
# src/core/tasks/workflow_tasks.py
_tid = task_data_dict.get("tenant_id")
if _tid is None:
    raise ValueError(
        f"tenant_id missing in task_data for task {task_data_dict.get('task_id')} — "
        "rejecting to prevent data isolation bypass (ADR-003)"
    )
set_tenant_id(_tid)
```

**Fix B — Single-tenant worker context decorator**
```python
# src/core/workers/tenant_context.py
from contextlib import contextmanager
from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id
from src.config import DEPLOYMENT_MODE

@contextmanager
def single_tenant_worker_context():
    """Vult tenant_id = 1 in voor workers in single_tenant mode."""
    if DEPLOYMENT_MODE == "single_tenant" and get_tenant_id() is None:
        set_tenant_id(1)
    yield

def ensure_single_tenant_context(func):
    """Decorator voor Dramatiq actors die tenant context vereisen."""
    import functools
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with single_tenant_worker_context():
            return func(*args, **kwargs)
    return wrapper
```

De decorator vervangt het silent-skip patroon: in single_tenant mode wordt tenant_id = 1 altijd gezet; in saas mode blijft Fix A het harde falen-pad.

> **S7 heroverweging (2026-07-02):** bij de re-audit bleek dat Fix A (hard-fail,
> TI-004) de daadwerkelijk geimplementeerde en geteste enforcement-strategie is
> voor ALLE dict-payload actors (zie `tests/architecture/test_dramatiq_actors_tenant_id.py`),
> terwijl Fix B (`single_tenant_worker_context` / `ensure_single_tenant_context`)
> als losstaand utility bestaat in `src/core/workers/tenant_context.py` met eigen
> groene tests, maar in productie nergens wordt aangeroepen. Dit is een bewuste
> keuze gebleken, geen omissie: fail-closed (Fix A) is strenger dan fail-open naar
> tenant_id=1 (Fix B) en dekt zowel saas als single_tenant met een enkel patroon.
> Fix B blijft beschikbaar als toekomstige optie voor actors die bewust een
> auto-fallback willen i.p.v. hard-fail, maar is GEEN vereiste voor ADR-035-sluiting.
> Succescriterium 4 hieronder is dienovereenkomstig geherformuleerd.

### D4 — Docker Compose + deployment documentatie

Single-tenant deployment vereist:

```
docker-compose.single-tenant.yml       # pre-geconfigureerd voor on-premise
.env.single-tenant.example             # alle vereiste env-vars met uitleg
docs/deployment/single-tenant-guide.md # stap-voor-stap installatiegids
```

Minimale vereiste env-vars:

```bash
DEPLOYMENT_MODE=single_tenant
DEFAULT_TENANT_NAME=<organisatienaam>
DEFAULT_TENANT_SLUG=<slug>
DEFAULT_ADMIN_EMAIL=<email>
DEFAULT_ADMIN_PASSWORD=<min 16 chars>
SECRET_KEY=<random 64 chars — gebruik: openssl rand -hex 32>
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
CORS_ALLOWED_ORIGINS=https://<jouw-domein>  # NOOIT * in productie (SEC-001)
```

> **SEC-001 (audit HIGH):** CORS-wildcards zijn verboden. `CORS_ALLOWED_ORIGINS` is verplicht in
> single-tenant deployments en wordt bij startup gevalideerd (fail-fast als leeg of `*`).

### D5 — Service-laag per domein (ADR-033 naleving)

Alle 13 resterende domeinen schenden ADR-033 via directe `get_db`-injectie in routers. Dit is geen single-tenant-specifiek probleem, maar blokkeert consistente testbaarheid voor single-tenant scenario's.

Beslissing: uitvoeren conform AUDIT-SINGLE-TENANT-DB01-volledig-plan.md, Fase B (4 weken, 13 domeinen). Elk domein krijgt:
- Architecture test (geverifieerd GROEN voor commit)
- Service-klasse met `_tenant_scope()` defense-in-depth
- `Depends(get_x_service)` i.p.v. `Depends(get_db)` in alle routers

Canonical patroon: commit `0a83fb5e` (AUDIT-DB-01 tenants, `src/core/api/v1/tenants/`).

---

## Alternatieven overwogen

### Alternatief A — Aparte codebase voor single-tenant

Twee codebases onderhouden (SaaS + single-tenant fork) verdubbelt de onderhoudslast.
Verworpen: één codebase met feature-flag is superieur.

### Alternatief B — X-Tenant-ID header als fallback

Een vaste header `X-Tenant-ID: 1` als alternatief voor JWT-claim.
Verworpen: ADR-003 verbiedt expliciet `X-Tenant-ID` headers als tenant-identity bron.
Bovendien: elke client moet die header meesturen — foutgevoelig en onnodig.

### Alternatief C — Aparte database per tenant (single-tenant = eigen DB)

DB-isolatie per tenant is de sterkste isolatievorm.
Verworpen voor MVP: migratie-complexiteit, geen multi-tenant pad meer mogelijk, out-of-scope voor de huidige klantbehoefte (Ketikoti Vlaardingen). Heroverwegen bij ADR-002 revisie als multi-DB vereist wordt.

### Alternatief D — Hardcoded VITE_WS_URL vereisen in single-tenant

Single-tenant klanten moeten `VITE_WS_URL` instellen; anders geen WS.
Verworpen: single-tenant klanten deployen vaak zonder custom frontend-build. De `window.location.host`-fallback werkt out-of-the-box.

---

## Consequenties

### Positief

- On-premise deployment mogelijk zonder codewijziging per klant
- Geen JWT-tenant-claim vereist — eenvoudigere auth voor interne tools
- Alle security-invarianten (ADR-003/ADR-004/ADR-005) blijven intact
- TI-004 (CRITICAL) fix verbetert ook de SaaS-worker betrouwbaarheid
- CORS-wildcard risico wordt geadresseerd als onderdeel van D4

### Negatief / Risico's

| Risico | Mitigatie |
|---|---|
| Klant zet per ongeluk `DEPLOYMENT_MODE=single_tenant` in productie-SaaS | `DEFAULT_TENANT_ID` in seed script is beschermd; middleware-fallback raakt alleen lege context |
| Foutieve Docker Compose configuratie lekt `SECRET_KEY` in logs | Startup-validatie controleert kritieke env-vars op aanwezigheid (niet op waarde) |
| Nieuwe dict-payload Dramatiq actor zonder tenant_id-validatie | `tests/architecture/test_dramatiq_actors_tenant_id.py` discovery-test faalt op elke nieuwe ongeregistreerde dict-payload actor (S7, GESLOTEN) |
| CORS misconfiguratie in single-tenant | Fail-fast validatie bij startup: ValueError als `CORS_ALLOWED_ORIGINS` leeg of `*` |

### Niet gewijzigd

- Database schema (geen migraties vereist)
- JWT-authenticatie voor gebruikers
- Alle bestaande ADRs (003, 004, 005, 006, 010, 033)
- Multi-tenant SaaS werking (DEPLOYMENT_MODE=saas is onveranderd)

---

## Succescriteria (meetbaar)

| Criterium | Maatstaf | Status |
|---|---|---|
| HTTP middleware fallback actief in single_tenant mode | `pytest tests/unit/middleware/test_tenant_middleware_single_tenant.py` GROEN | GESLOTEN (5c461bd7) |
| 0 hardcoded wss://api.sanskritisetu.org in productie-bronbestanden | `grep -rn "wss://api.sanskritisetu.org" frontend/src --include="*.ts" --include="*.tsx"` = 0 matches (S7 preventietest: `frontend/src/__tests__/architecture/no-hardcoded-ws-urls.test.ts`) | GESLOTEN (60b1d64f, preventie S7) |
| docker-compose.single-tenant.yml aanwezig en gevalideerd | `pytest tests/architecture/test_single_tenant_deployment.py` GROEN (3/3) | GESLOTEN (60b1d64f) |
| Fail-closed tenant_id-enforcement op alle dict-payload Dramatiq actors (D3 Fix A, zie heroverweging hierboven -- Fix B decorator is bewust niet geadopteerd) | `pytest tests/architecture/test_dramatiq_actors_tenant_id.py` GROEN (2/2, incl. discovery-scan tegen nieuwe ongeregistreerde actors) | GESLOTEN (S7 preventietest) |
| TI-004 gefixed: workflow task rejecteert bij missing tenant_id | `pytest tests/unit/tasks/test_workflow_tasks_tenant_context.py` GROEN (2/2) | GESLOTEN (60b1d64f) |
| detect_db_imports.py: 0 offenders in alle 13 domeinen | `python scripts/detect_db_imports.py` exit code 0, 69 gescand, 0 offenders | GESLOTEN (492bfe07) |
| Single-tenant smoke test slaagt | Stack start met DEPLOYMENT_MODE=single_tenant; `/health` -> `{"status":"ok"}`, `/health/ready` -> `{"status":"ready","dependencies":{"database":"connected","redis":"connected"}}` | GESLOTEN (S7, 2026-07-02, handmatig geverifieerd) |
| CORS fail-fast: startup ValueError bij CORS_ALLOWED_ORIGINS=* | `pytest tests/unit/middleware/test_cors_fail_fast.py tests/architecture/test_single_tenant_env_no_cors_wildcard.py` GROEN (5/5), `validate_cors_config` gewired in `middleware_config.py` | GESLOTEN (492bfe07 + 6d657a13) |

---

## Koppeling aan andere ADRs

| ADR | Relatie |
|---|---|
| ADR-003 | Tenant identity via ContextVar — single-tenant vult de context aan, vervangt de bron niet |
| ADR-004 | ORM `do_orm_execute` hook — werkt ongewijzigd, tenant_id = 1 is een normale waarde |
| ADR-005 | DB hardening NOT NULL + RLS — ongewijzigd, tenant_id = 1 voldoet aan NOT NULL constraint |
| ADR-006 | Dramatiq + Redis — worker-decorator vereist vanwege buiten-lifecycle execution |
| ADR-010 | Gunicorn + Uvicorn — deployment-configuratie relevant voor docker-compose.single-tenant.yml |
| ADR-033 | Service-laag per domein — D5 is co-afhankelijk; single-tenant test coverage vereist service-laag |

---

## Implementatieplan

Zie `docs/plans/AUDIT-SINGLE-TENANT-DB01-volledig-plan.md` voor het volledige 27-daagse sprint-plan.

Samenvatting per beslissing:

| Beslissing | Sprint-dag(en) | Audit-item |
|---|---|---|
| D1 middleware (al gedaan) | — | AUDIT-TENANT-01 GESLOTEN |
| D2 frontend WebSocket URLs | Dag 1 | AUDIT-ST-01 |
| D3 TI-004 fix + worker decorator | Dag 3 | TI-004 + AUDIT-ST-03 |
| D4 Docker + deployment docs | Dag 2 | AUDIT-ST-02 |
| D5 service-laag 13 domeinen | Dag 4–22 | AUDIT-DB-02..14 |

---

## Open punten

| ID | Omschrijving | Prioriteit | Sprint |
|---|---|---|---|
| OP-01 | ~~Architecture test: alle Dramatiq actors scannen op `@ensure_single_tenant_context`~~ -- GESLOTEN via alternatieve route: `tests/architecture/test_dramatiq_actors_tenant_id.py` scant op fail-closed tenant_id-validatie (Fix A) i.p.v. decorator-aanwezigheid (Fix B), zie S7-heroverweging | P1 | S7 GESLOTEN |
| OP-05 | Fix A (hard-fail) werkt alleen omdat alle huidige callers van dict-payload actors een geauthenticeerde HTTP-context hebben (JWT -> tenant_id). Een toekomstige scheduled/cron actor zonder JWT-context zou hard falen i.p.v. gracieus tenant_id=1 te krijgen in single_tenant mode. Geen test/contract bewaakt dit scenario -- `single_tenant_worker_context` (Fix B) bestaat als ongebruikte fallback in `src/core/workers/tenant_context.py` mocht dit ooit nodig zijn. Onafhankelijke review S7 (2026-07-02). | P2 | Post-MVP (activeren zodra een scheduled Dramatiq actor zonder JWT-context wordt toegevoegd) |
| OP-02 | Multi-tenant → single-tenant migratie-gids (bestaande SaaS-klant wil on-premise) | P2 | Post-MVP |
| OP-03 | Single-tenant licentiemodel — meerdere organisaties op zelfde installatie? | P2 | Product beslissing |
| OP-04 | Multi-database single-tenant (alternatief C) heroverwegen bij >10 gelijktijdige single-tenant klanten | P2 | ADR-002 revisie |

---

*Eigenaar: Rakesh Ramkhelawan | Aangemaakt: 2026-06-29*
*Gebaseerd op: AUDIT-TENANT-01 (commit 5c461bd7) + multidisciplinaire audit 2026-06-29 (77 bevindingen) + docs/plans/AUDIT-SINGLE-TENANT-DB01-volledig-plan.md*
