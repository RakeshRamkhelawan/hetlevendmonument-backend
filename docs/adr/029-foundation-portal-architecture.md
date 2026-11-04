# ADR-029: Foundation Portal Architecture

## Status

Proposed | 2026-04-26 | Author: Rakesh Ramkhelawan | Reviewers: TBD

## Context

Stichting Ketikotivlaardingen.NL heeft een SUMS Categorie 2 subsidie
(BWBR0049978, € 19.625 + opslagen tot € 23.719 totaal) verkregen voor het
bouwen van een **Levend Monument** — een digitaal platform waar nazaten
van tot slaaf gemaakten verhalen, kunst en kennis kunnen delen.

SanskritiSetu wordt het technisch fundament. De bredere visie: alle
Nederlandse stichtingen kunnen via SanskritiSetu een Foundation Portal
opzetten met content-curatie, AI-tagging en multi-tenant white-labeling.
Door één centrale Next.js deployment met hostname-routing kunnen we
50+ stichtingen bedienen zonder lineaire ops-kosten.

### Eisen

1. **Multi-tenant white-labeling**: meerdere stichtingen met eigen subdomain,
   branding, content. Volledige data-isolatie (cross-tenant lookup mag
   absoluut nul rijen retourneren).
2. **Open source verdienmodel**: portal-code MIT op GitHub; verdienen aan
   implementatie + hosting + beheer + enterprise-features.
3. **AVG + WCAG 2.1 AA + NTD-procedure**: vereist voor publiek
   erfgoedplatform met overheidsfinanciering.
4. **Lage drempel voor uploaders**: nazaten zijn niet allemaal tech-savvy;
   geen wachtwoord-flows — magic-link e-mail.
5. **AI-ondersteunde curatie**: automatische metadata-extractie (thema,
   locatie, periode, sentiment, taal) via LLM. Suggesties, geen
   auto-publicatie.
6. **Schaalbaar zonder lineaire kostenstijging**: 1 deployment moet 50+
   stichtingen kunnen bedienen.
7. **Hergebruik bestaande SanskritiSetu-infrastructuur**: audit-hash chain
   (ADR-019), ORM-hook tenant filtering (ADR-004), Dramatiq workers
   (ADR-006), Traefik TLS (ADR-009).

### Alternatieven

| Optie | Voordeel | Nadeel | Besluit |
|---|---|---|---|
| **A. Content Portal module binnen SanskritiSetu** | 1 deployment, 1 codebase, hergebruik bestaande infra | SanskritiSetu admin UI niet geschikt als publieksgerichte portal; zware coupling met dashboard | Afgewezen |
| **B. Decoupled Next.js portal + SanskritiSetu backend (publieke API)** | Portal MIT open source; backend privacy; multi-tenant via hostname-routing | Twee deployments te onderhouden | **Gekozen** |
| **C. Stichting forkt en host zelf** | Volledige autonomie per stichting | Schaal-ramp: 50 stichtingen = 50 deployments + 50 helpdesks | Afgewezen |
| **D. Self-service builder in SanskritiSetu dashboard** | Stichtingen configureren zelf | Te ambitieus voor MVP; bouwen na 2e tenant | Fase 2 (post-MVP) |

## Decision

We bouwen het Foundation Portal als **decoupled architectuur (optie B)**.

### High-level architectuur

```
                       ┌─────────────────────────────────────┐
   ketikoti.lm.nl  ───▶│                                     │
   stichting-b.lm.nl ─▶│   Next.js 14 (App Router, MIT)      │── ISR cache
   custom.example.nl ▶│   Eén Azure Container App-deploy    │   (60s TTL)
                       │   Hostname → tenant_slug resolution │
                       └────────────────┬────────────────────┘
                                        │
                                        │ HTTPS (Traefik TLS 1.3)
                                        ▼
                       ┌─────────────────────────────────────┐
                       │  Traefik edge (ADR-009)             │
                       │  - X-Forwarded-For injection        │
                       │  - maxRequestBodySize middleware    │
                       │  - StripPrefix per route            │
                       └────────────────┬────────────────────┘
                                        │
                                        ▼
                       ┌─────────────────────────────────────┐
                       │  SanskritiSetu FastAPI (Gunicorn)   │
                       │  /api/v1/public/{tenant_slug}/...   │
                       │  - resolve_tenant_by_slug()          │
                       │  - set_tenant_id() → ORM hook       │
                       │  - rate-limit (IP/email)             │
                       └──┬──────────┬──────────────┬────────┘
                          │          │              │
                          ▼          ▼              ▼
                 ┌──────────────┐ ┌─────────┐ ┌──────────────┐
                 │ PostgreSQL   │ │ Redis   │ │ Dramatiq     │
                 │ + pgvector   │ │ broker  │ │ workers       │
                 │ (tenant RLS) │ │ + cache │ │ (AI-tagging)  │
                 └──────────────┘ └─────────┘ └──────┬───────┘
                                                      │
                                                      ▼
                                            ┌──────────────────┐
                                            │ Ollama           │
                                            │ mistral:7b-instr │
                                            │ (NL tagging LLM) │
                                            └──────────────────┘

   ┌──────────────┐    ┌──────────────┐
   │ Azure Blob   │    │ Brevo        │
   │ - GRS        │    │ - magic-link │
   │ - soft-delete│    │ - newsletter │
   │ - versioning │    └──────────────┘
   └──────────────┘
```

### Componenten

1. **Frontend** — Next.js 14 (App Router, TypeScript, Tailwind, Radix UI)
   als aparte MIT-repo `levend-monument-portal`. Eén centrale Azure
   Container App-deployment serveert alle stichtingen via hostname-based
   slug-routing. ISR met TTL 60s, on-demand revalidatie via
   `POST /api/revalidate` (signed door backend).

2. **Backend** — uitbreiding van SanskritiSetu met:
   - 7 nieuwe modellen: `FoundationContent`, `ContentTag`,
     `FoundationPortalSettings`, `PortalUser`, `MagicLinkToken`,
     `TakedownRequest`, `NewsletterSubscription` (in 5 Alembic-migraties).
   - Publieke API onder `/api/v1/public/{tenant_slug}/`. Deze prefix staat
     in `PUBLIC_PREFIXES` zodat `TenantMiddleware` wordt omzeild; handlers
     lossen `tenant_slug → tenant_id` zelf op via `resolve_tenant_by_slug()`
     en activeren de ORM-hook (ADR-004) via `set_tenant_id()`.
   - Magic-link auth (passwordless) voor uploaders, e-mail via Brevo
     transactional, JWT met `scope=portal_uploader` claim (gescheiden van
     `scope=admin`).
   - AI-tagging service via Ollama `mistral:7b-instruct` als Dramatiq-job
     (ADR-006). Suggesties met confidence-score; curator-validatie verplicht.
   - 6 nieuwe rate limiters (5 IP-based + 1 e-mail-based voor
     magic-link anti-spam).
   - Educatieve endpoints: `POST /public/{slug}/edu/access` (code-validatie),
     `GET /public/{slug}/edu/content` (lijst + detail, vereist
     `edu_session` cookie), `POST /public/{slug}/edu/content` (docent-upload).
   - Kaart-API: `GET /public/{slug}/map/bbox?sw_lat=...&ne_lon=...`
     retourneert geo-JSON FeatureCollection van approved content met
     lat/lon binnen de bounding box.
   - OAI-PMH endpoint: `GET /public/{slug}/oai-pmh?verb=ListRecords`
     met Dublin Core output; rate-limited op 100/min per IP.

3. **Multi-tenancy** — via bestaande `Tenant.slug` (al uniek-geïndexeerd in
   `rbac_models.py`). Subdomain-routing fase 1; custom-domain fallback
   fase 2 via DB-lookup met Redis-cache.

4. **TLS** — fase 1 per-subdomain `httpChallenge` (bestaande Traefik-config
   volstaat, ADR-009). Wildcard via `dnsChallenge` is fase 2 zodra de
   `*.levend-monument.nl` DNS-zone op ons account staat.

5. **Storage** — Azure Blob met magic-bytes MIME-validatie + GRS +
   soft-delete + versioning. Per tenant een container `tenant-{tenant_id}/`,
   private access, SAS-URLs (15 min TTL) voor uploads.

6. **Auth** — magic-link e-mail (15 min TTL, SHA-256 token-hash in DB,
   nooit raw token persisteren) + JWT met `scope=portal_uploader` claim
   (gescheiden van admin-scope). hCaptcha vóór magic-link aanvraag tegen
   e-mail-bombing.

7. **Compliance** — AVG-DSAR + delete-flows; WCAG 2.1 AA met
   axe-core/Lighthouse CI; NTD-procedure conform art. 6:196c BW;
   Creative Commons BY-NC-SA 4.0 license per item; cookie consent via
   bestaande SanskritiSetu Consent API.

8. **Commercialisering & Feature-Gating** — We benutten SanskritiSetu's
   ingebouwde `FeatureFlagManager` (`src/core/feature_flags/manager.py`)
   en `Tier` enum (`src/core/feature_flags/features.py`: `FREE`, `STARTER`,
   `PRO`, `ENTERPRISE`) om enterprise-functionaliteiten selectief aan te
   bieden aan stichtingen (tenants):
   - **FREE** (€0/maand): demo/trial tier — Foundation Portal NIET inbegrepen.
     Stichtingen die het Levend Monument willen draaien starten minimaal
     op STARTER.
   - **STARTER** (€0/maand): publieke Levend Monument portaal, basis
     AI-tagging, standaard rate limits (60 req/min), 1 GB content-opslag,
     gedeeld subdomain `{slug}.levend-monument.nl`.
   - **PRO** (commercieel, ~€49/maand baseline, aanpasbaar voor stichtingen):
     custom-domein, custom white-label branding, advanced analytics
     dashboard, toegang tot het SanskritiSetu Collaborative Canvas,
     10 GB content-opslag, hogere rate limits (300 req/min).
   - **ENTERPRISE** (commercieel, vanaf €499/maand, custom pricing >100 users):
     ongelimiteerde specialist AI-agents (bv. automatische
     archieftranscriptie), SSO, volledige compliance-audit logs, dedicated
     support SLA, 100 GB content-opslag.
   - **Console-toegang:** publieke uploaders en lezers blijven strikt
     geïsoleerd op de Next.js portal (geautoriseerd via JWT met
     `scope=portal_uploader`). Stichtingsbeheerders/curatoren loggen in op
     de centrale *SanskritiSetu Console* (Dashboard) waar ze, afhankelijk
     van hun `Tenant.plan` tier, toegang krijgen tot de geactiveerde
     enterprise-functionaliteiten.

### Subsidie-gedreven portal-uitbreidingen (Cat 3 & Cat 4)

De subsidieaanvragen Categorie 3 (Euro 117.875, 24 maanden) en Categorie 4
(~Euro 488.000, 48 maanden) stellen functionele eisen aan het platform die
bovenop het Cat 2-MVP (5 items, basis portal) moeten worden gerealiseerd.
De volgende vijf uitbreidingen zijn **architectuur-vereisten** om aan de
verplichtingen van UVB te voldoen:

1. **Educatieve leeromgeving (afgeschermd)** — Een aparte sectie op het
   portal voor lesmateriaal (werkboeken, korte videolessen,
   docentenhandleidingen). Leerlingen krijgen **geen individuele accounts**;
   in plaats daarvan ontvangt een docent per klas/school een
   `edu_access_code` (8 karakters, alfanumeriek). Bij invoer wordt een
   sessie-cookie gezet (TTL = 4 schooluren). `FoundationContent` krijgt
   veld `visibility: public | edu | community`. Alleen `public` content
   verschijnt in het openbare verhalenarchief; `edu` content is alleen
   bereikbaar via `/edu/*` routes en vereist een geldige sessie. Dit
   voorkomt complex youth-account beheer en voldoet aan de AVG-minimale-
   data-eis voor scholen.

2. **Kaartweergave met geo-koppeling** — Verhalen en content worden
   gekoppeld aan fysieke plekken in Vlaardingen (bijv. Ketikoti Plein,
   Geuzenmuseum). `FoundationContent` krijgt optionele geo-velden
   (`latitude`, `longitude`, `location_name`). De publieke API biedt
   `GET /public/{slug}/map/bbox` voor bounding-box queries (gebruikmakend
   van B-tree indexen op lat/lon; geen PostGIS vereist voor MVP). De
   Next.js frontend rendert markers via MapLibre GL JS (open source,
   geen API key, WCAG-compatibele contrasten).

3. **Polymorfe content-types** — Het platform ondersteunt naast
   "verhaal" ook: `video`, `audio`, `educational_workbook`,
   `educational_video`, `teacher_guide`, `event_report`,
   `art_documentation`. `FoundationContent.content_type` is een enum
   met bijbehorende `metadata` JSONB-validatie per type (bijv.
   `target_age_group` voor educational, `duration_seconds` voor
   video/audio). Het Next.js portal laadt per type een ander
   render-component en toont type-specifieke metadata.

4. **Archivering & metadata-export (duurzame toegankelijkheid)** —
   Conform Cat 4-eis "toegankelijkheid en archivering" biedt het platform
   een OAI-PMH endpoint (`/public/{slug}/oai-pmh`) voor metadata-harvesting
   in Dublin Core. Elk item draagt verplicht een Creative Commons
   BY-NC-SA 4.0 licentie (`FoundationContent.license`, default
   `CC-BY-NC-SA-4.0`). Een wekelijkse Dramatiq-job exporteert nieuwe/
   gewijzigde items naar statische JSON (BagIt-structuur) voor depositie
   in een extern digitaal archief (fase 4).

5. **School- en docententoegang** — `PortalUser.role` wordt uitgebreid
   met `teacher` (naast `uploader` en `curator`). Docenten registreren
   zich via een vereenvoudigd formulier (naam, school, e-mail); de
   curator activeert het account. Een geactiveerde docent kan
   `edu_access_codes` aanmaken voor eigen klassen. Uploads door docenten
   komen in een aparte educatieve curatie-queue.

### Datamodel — overzicht

```
Tenant (bestaand) ───┬───< FoundationContent ───< ContentTag (JOIN-isolatie)
                     │         └───< EducationalAccess (tenant-scoped school-codes)
                     ├───< FoundationPortalSettings (1:1)
                     ├───< PortalUser ───< MagicLinkToken
                     │         └────────< FoundationContent (uploader_id)
                     ├───< TakedownRequest ──> FoundationContent
                     ├───< NewsletterSubscription
                     └───< EducationalAccess (tenant-scoped school-codes)
```

Alle modellen behalve `ContentTag` hebben `tenant_id NOT NULL` met FK naar
`tenants.id ON DELETE CASCADE`. `ContentTag` heeft géén eigen `tenant_id`
omdat die deterministisch volgt uit `FoundationContent.tenant_id`; dit
voorkomt drift tussen `ContentTag.tenant_id` en `FoundationContent.tenant_id`
bij content-migratie.

**Nieuw in Cat 3/Cat 4 uitbreiding:**
- `FoundationContent` krijgt velden: `content_type` (enum, NOT NULL),
  `visibility` (enum `public`/`edu`/`community`, default `public`),
  `latitude`/`longitude` (nullable FLOAT, geindexeerd), `location_name`
  (nullable VARCHAR(255)), `license` (VARCHAR(50), default
  `CC-BY-NC-SA-4.0`), `target_age_group` (nullable VARCHAR(20)).
- `EducationalAccess` (tenant_id FK, school_name, access_code_hash,
  teacher_email, expires_at, created_at). Een hash (SHA-256) van de
  ruwe code wordt opgeslagen; de ruwe code wordt nooit gepersisteerd.
  TTL wordt afgedwongen in de query, niet door DB-level constraints.
- Geo-isolatie: bounding-box queries filteren altijd eerst op tenant_id
  via de ORM-hook; daarna pas op lat/lon. Dit voorkomt dat tenant A
  markers van tenant B ziet.

### Belangrijke isolatie-uitzonderingen (gedocumenteerd, geen lek)

- **`ContentTag`** heeft géén eigen `tenant_id`. Isolatie loopt via JOIN op
  `FoundationContent`. De ORM `do_orm_execute` hook (ADR-004) filtert
  ContentTag NIET zelfstandig — queries MOETEN altijd via JOIN of subquery
  op `FoundationContent.id` lopen. Geverifieerd in
  `tests/security/test_foundation_tenant_isolation.py::test_content_tag_join_isolation`.

- **Public endpoints** onder `/api/v1/public/` staan in `PUBLIC_PREFIXES` en
  omzeilen `TenantMiddleware`. Handlers lossen `tenant_slug → tenant_id`
  zelf op via `resolve_tenant_by_slug()` en roepen daarna `set_tenant_id()`
  aan zodat de ORM-hook activeert. Rate-limit key gebaseerd op IP
  (`X-Forwarded-For` first value van Traefik), nooit op een
  client-controlled tenant-header.

### Sequence diagrammen

#### Magic-link authentication

```
Uploader        Next.js Portal      FastAPI Backend       Brevo SMTP        DB
   │                 │                    │                   │              │
   │ vul e-mail in   │                    │                   │              │
   ├────────────────▶│                    │                   │              │
   │                 │ POST /public/{s}/magic-link            │              │
   │                 ├───────────────────▶│                   │              │
   │                 │                    │ hCaptcha verify   │              │
   │                 │                    ├──────────────────▶│              │
   │                 │                    │◀──────────────────┤              │
   │                 │                    │ resolve_tenant    │              │
   │                 │                    ├───────────────────────────────▶│
   │                 │                    │◀───────────────────────────────┤
   │                 │                    │ generate token (32b URL-safe)  │
   │                 │                    │ store SHA-256 hash + TTL 15min │
   │                 │                    ├───────────────────────────────▶│
   │                 │                    │ send mail with link            │
   │                 │                    ├──────────────────▶│              │
   │                 │ 202 Accepted       │                   │              │
   │                 │◀───────────────────┤                   │              │
   │ mail aankomen   │                                                     │
   │◀────────────────────────────────────────────────────────┤              │
   │ klik magic-link │                    │                   │              │
   ├────────────────▶│                    │                   │              │
   │                 │ GET /verify?token={raw}                │              │
   │                 ├───────────────────▶│                   │              │
   │                 │                    │ lookup SHA-256 hash, check TTL │
   │                 │                    ├───────────────────────────────▶│
   │                 │                    │ mark consumed, issue JWT       │
   │                 │                    │ (scope=portal_uploader, exp=24h)│
   │                 │ 200 + set-cookie   │                                 │
   │                 │◀───────────────────┤                                 │
   │ logged in       │                                                     │
   │◀────────────────┤                    │                                 │
```

#### Content upload + AI-tagging

```
Uploader   FastAPI   Azure Blob   Dramatiq   Ollama    Curator UI
   │          │          │            │         │          │
   │POST /content (multipart)         │         │          │
   ├─────────▶│          │            │         │          │
   │          │ magic-bytes MIME check│         │          │
   │          │ generate SAS URL      │         │          │
   │          ├─────────▶│            │         │          │
   │          │◀─────────┤            │         │          │
   │          │ INSERT FoundationContent status=PENDING    │
   │          │ enqueue ai_tag(content_id)                 │
   │          ├──────────────────────▶│         │          │
   │ 201 Created                      │         │          │
   │◀─────────┤          │            │         │          │
   │          │          │            │ fetch content      │
   │          │          │            ├────────▶│          │
   │          │          │            │ prompt + content   │
   │          │          │            ├────────▶│          │
   │          │          │            │◀────────┤ tags+conf│
   │          │          │            │ INSERT ContentTag* │
   │          │          │            │ (confidence ≥ 0.50)│
   │          │          │            ├────────────────────│
   │          │ Curator opens queue, sees PENDING + AI-tags│
   │          │◀───────────────────────────────────────────┤
   │          │ POST /admin/content/{id}/approve          │
   │          │◀───────────────────────────────────────────┤
   │          │ UPDATE status=APPROVED                     │
   │          │ audit_log (best_effort, hash chain ADR-019)│
   │          │ trigger ISR revalidate Next.js             │
   │          ├──────────────────────▶│                    │
```

#### Tenant resolution voor publieke request

```
Next.js                     Traefik                 FastAPI
   │ HTTP/2 ketikoti.lm.nl/api/v1/public/ketikoti/content
   ├────────────────────────▶│
   │                         │ inject X-Forwarded-For
   │                         │ TLS terminate
   │                         ├────────────────────────▶│
   │                         │                         │ path: /api/v1/public/ketikoti/content
   │                         │                         │ → in PUBLIC_PREFIXES, skip TenantMiddleware
   │                         │                         │ handler: resolve "ketikoti" via DB
   │                         │                         │ validate_slug() → ok
   │                         │                         │ SELECT Tenant WHERE slug=$1 AND is_active=true
   │                         │                         │ → tenant.id = 42
   │                         │                         │ set_tenant_id(42) → ContextVar
   │                         │                         │ ORM hook auto-filters
   │                         │                         │ SELECT FoundationContent WHERE status='approved'
   │                         │                         │ (hook injects AND tenant_id=42)
   │                         │                         │ → 23 rows
   │                         │                         │ clear_tenant_context() in finally
   │                         │ 200 JSON                │
   │                         │◀────────────────────────┤
   │ 200 JSON                │
   │◀────────────────────────┤
```

#### NTD takedown

```
Klager   Next.js   FastAPI   Curator UI   DB           Storage
  │         │         │           │         │              │
  │ form    │         │           │         │              │
  ├────────▶│         │           │         │              │
  │ POST /takedown    │           │         │              │
  │         ├────────▶│           │         │              │
  │         │ rate-limit IP (5/h) │         │              │
  │         │ INSERT TakedownRequest status=PENDING        │
  │         │         ├──────────────────▶│                │
  │         │ 202 Accepted        │                        │
  │         │◀────────┤           │         │              │
  │         │         │ NEW takedown alert (websocket)     │
  │         │         │           │◀────────┤              │
  │         │         │ Curator inspecteert, beslist        │
  │         │ POST /admin/takedown/{id}/approve            │
  │         │         │◀──────────┤                        │
  │         │         │ UPDATE FoundationContent status=REMOVED │
  │         │         │ soft-delete blob (versioned)        │
  │         │         ├───────────────────────────────────▶│
  │         │         │ trigger ISR revalidate              │
  │         │         │ audit_log (immutable, hash chain)   │
  │         │         │ notify klager via Brevo             │
  │         │         │ within 7 days SLA                   │
```

#### Tier-upgrade flow (Stripe, post-MVP roadmap)

```
Beheerder  Console UI   FastAPI    Stripe Checkout   Stripe Webhook  DB
   │          │            │              │                │            │
   │ klik 'upgrade Pro'    │              │                │            │
   ├─────────▶│            │              │                │            │
   │          │POST /billing/checkout-session             │            │
   │          ├───────────▶│              │                │            │
   │          │            │ create Checkout Session       │            │
   │          │            │ (with tenant_id in metadata)  │            │
   │          │            ├─────────────▶│                │            │
   │          │            │◀─────────────┤ session_url    │            │
   │          │ redirect   │              │                │            │
   │          │◀───────────┤              │                │            │
   │ vul kaart in                         │                │            │
   ├──────────────────────────────────────▶│                │            │
   │                                       │ checkout.session.completed │
   │                                       ├────────────────▶│           │
   │                                       │                │ idempotency: skip if event_id seen
   │                                       │                │ verify signature (HMAC-SHA256)
   │                                       │                │ UPDATE Tenant.plan='pro'
   │                                       │                ├──────────▶│
   │                                       │                │ FeatureFlagManager.invalidate(tenant_id)
   │                                       │                │ audit_log (best_effort)
   │ confirm                               │                │            │
   │◀──────────────────────────────────────┤                │            │
```

### Non-Functional Requirements

| Aspect | Doel | Meting |
|---|---|---|
| **Edu access code lookup** | < 100ms p99 | Redis-backed code cache + unit benchmark |
| **Map bbox query** | < 150ms p95 | DB index + query plan check |
| **OAI-PMH ListRecords** | < 500ms voor sets van 100 records | Pagination + DB index |
| **Content type validation** | < 10ms per item | Schema validatie benchmark |
| **Page load (homepage)** | TTFB < 800ms, LCP < 2.5s | Lighthouse CI per PR |
| **Public API p95 latency** | < 250ms (read), < 600ms (write zonder file) | Prometheus histogram |
| **AI-tagging latency** | p95 < 30s (async, Dramatiq) | Job duration metric |
| **Magic-link e-mail delivery** | < 60s vanaf POST tot inbox | Brevo webhook timing |
| **Upload max size** | 100 MB per file | Traefik `maxRequestBodySize` |
| **Availability** | 99.5% (3.6h downtime/maand) | Azure SLA + UptimeRobot |
| **Backup RPO** | 24h (PostgreSQL dump dagelijks) | Azure Backup Vault |
| **Backup RTO** | 4h (restore + Alembic) | Quarterly DR drill |
| **WCAG** | 2.1 AA op alle 14 pagina's | axe-core E2E, Lighthouse ≥ 95 |
| **Concurrent users** | 500 active sessions per tenant | Load test (k6) vóór go-live |
| **Cross-tenant isolation** | 100% — nul rijen lek bij verkeerde context | Security test (verplicht in CI) |
| **Slug-validatie** | < 1ms per call | unit-test benchmark |
| **Rate-limit redis-roundtrip** | < 5ms p99 | slowapi + Redis metrics |

### Security threat model (STRIDE-light)

| Bedreiging | Mitigatie | Test |
|---|---|---|
| **Spoofing** — aanvaller raadt magic-link token | 256-bit token, SHA-256 hash in DB, 15min TTL, eenmalig consumeerbaar | Unit + integration |
| **Spoofing** — verlopen JWT hergebruikt | `exp` claim verplicht (`require_exp=True`), JTI blacklist optioneel | JWT-pad unificatie tests |
| **Tampering** — tenant-id in body of header | `tenant_id` ALLEEN uit `resolve_tenant_by_slug()`; rate-limit-key uit `X-Forwarded-For` (Traefik), nooit header | `test_rate_limiter_no_header_fallback` |
| **Repudiation** — content geupload, uploader ontkent | Audit-log met hash chain (ADR-019); IP + user-agent + portal_user_id per actie | Hash chain integriteit test |
| **Information disclosure** — cross-tenant lek | ORM-hook (ADR-004) + `set_tenant_id()` in `public_tenant_scope`; isolation-tests verplicht in CI; RLS policies fase 2 (ADR-005) | `test_foundation_tenant_isolation.py` (7 modellen) |
| **Information disclosure** — slug-enumeratie | 404 voor zowel onbekend als inactief; geen onderscheid in foutboodschap | `test_resolve_raises_for_inactive_tenant` |
| **Information disclosure** — directe Blob URL | SAS-URL met 15min TTL, IP-restricted; geen public read op container | Storage-config test |
| **DoS** — magic-link e-mail bombing | `portal_magic_link_email_limit` (3/uur per e-mail), hCaptcha v3 score-threshold | Rate-limit test + hCaptcha mock |
| **DoS** — large-file upload | Traefik `maxRequestBodySize=100MB`; magic-bytes check vóór streaming naar Blob | Upload-grootte test |
| **DoS** — slow-loris / connection pool exhaustion | Gunicorn `worker_class=uvicorn.workers.UvicornWorker`, `timeout=30`, `max_requests=1000` | Chaos test (ADR-011) |
| **Elevation of privilege** — uploader gebruikt admin-scope | JWT `scope=portal_uploader` ≠ `scope=admin`; admin-endpoints in aparte router met `require_admin` guard | RBAC test |
| **Elevation of privilege** — Stripe webhook frauduleus | HMAC-SHA256 signature verify met `STRIPE_WEBHOOK_SECRET`; idempotency op `event.id` (post-MVP) | Webhook-signature test |
| **NTD-non-compliance** (art. 6:196c BW) | 7-day SLA, audit-log per beslissing, escalatie-route bij dispute | Workflow test + manual audit |
| **SLA-non-compliance AVG** | DSAR-export endpoint, delete-flow met soft-delete + 30-day grace period | E2E DSAR test |
| **Account takeover via stolen magic-link** | Token eenmalig consumeerbaar (transactional UPDATE...RETURNING); IP-fingerprint match optioneel | Race-condition test |

### Caching architectuur

| Cache | TTL | Invalidatie | Reden |
|---|---|---|---|
| **ISR Next.js (homepage, browse, detail)** | 60s | On-demand `POST /api/revalidate` (HMAC-signed) bij content APPROVE/REJECT/REMOVE | Eindgebruiker ziet content binnen 1 min |
| **Tenant slug → id (Redis)** | 300s | PUB/SUB `tenant:slug:changed` | Tenant.slug verandert zelden |
| **Custom-domain → tenant_id (Redis, fase 2)** | 60s | PUB/SUB `tenant:domain:changed` | DNS-wijziging propagatie |
| **Feature flags per tenant (memory + Redis)** | 60s | PUB/SUB `tenant:plan:changed` bij Stripe upgrade | Hot path, lage tolerantie voor staleness |
| **Rate-limit buckets (Redis)** | Per limiter (60s tot 24h) | TTL-based | slowapi convention |
| **Magic-link tokens** | 15min (TTL in DB) | UPDATE bij consume | Eenmalig gebruik |
| **AI-tagging cache** | Niet gecached — Dramatiq job is enige caller | n.v.t. | One-shot per content |

### Rate-limit policy

| Endpoint | Limit | Key | Reden |
|---|---|---|---|
| `GET /public/{slug}/content` | 60/min | IP | Pageload-friendly |
| `GET /public/{slug}/content/{id}` | 60/min | IP | Idem |
| `GET /public/{slug}/settings` | 60/min | IP | Idem |
| `POST /public/{slug}/magic-link` | 5/min | IP | Anti-spam |
| `POST /public/{slug}/magic-link` | 3/uur | e-mail | Anti-spam per e-mail (extra) |
| `POST /public/{slug}/verify` | 5/min | IP | Brute-force protection op token |
| `POST /public/{slug}/content` (auth) | 10/min | IP | Upload throttle |
| `POST /public/{slug}/takedown` | 5/uur | IP | NTD-spam protection |
| `POST /public/{slug}/newsletter/subscribe` | 3/uur | IP | Anti-spam |
| `GET /public/{slug}/me/export` (DSAR) | 3/uur | tenant_id+user_id | Anti-abuse |

### Geraakte ADRs

| ADR | Hoe geraakt |
|---|---|
| ADR-002 | Multi-tenancy shared DB — alle nieuwe tabellen volgen patroon |
| ADR-003 | JWT tenant identity — PortalUser-JWT bevat `tenant_id` + `scope=portal_uploader` |
| ADR-004 | ORM hook — `ContentTag` bewust uitgezonderd, gedocumenteerd |
| ADR-005 | `tenant_id NOT NULL` — alle nieuwe modellen voldoen (behalve ContentTag, JOIN-based) |
| ADR-006 | Dramatiq + Redis — AI-tagging als async job; e-mail-verzending idem |
| ADR-009 | Traefik TLS — nieuwe `maxRequestBodySize` middleware label; httpChallenge per subdomain |
| ADR-010 | Gunicorn workers — geen wijziging, bestaande config volstaat |
| ADR-013 | Gitleaks — nieuwe secrets (`BREVO_API_KEY`, `HCAPTCHA_SECRET`, `STRIPE_WEBHOOK_SECRET`, `AZURE_BLOB_CONNECTION_STRING`) in allowlist-test |
| ADR-014 | Observability — nieuwe metrics + traces + logs voor portal; `tenant_slug` toegevoegd als label |
| ADR-015 | ToolBroker — niet geraakt (geen agent-tool-calls vanuit portal) |
| ADR-019 | Audit log — content APPROVE/REJECT/REMOVE + takedown in hash chain |
| ADR-026 | Failover LLM — Ollama is primary, OpenAI fallback via `FailoverLLMProvider` |
| ADR-027 | Council — niet geraakt (council werkt op agents, niet op user-content) |

## Consequences

### Positief

- Portal-code MIT op GitHub creëert reputationele en commerciële waarde voor SanskritiSetu
- Eén centrale Next.js deployment schaalt naar 50+ stichtingen zonder lineaire ops-kosten
- Bestaande SanskritiSetu compliance-infrastructuur (audit-log, AVG, RBAC) wordt hergebruikt
- Magic-link auth elimineert wachtwoord-complexiteit en password-reset-flows
- WCAG 2.1 AA + AVG + NTD out-of-the-box differentieert van Omeka/Mukurtu/StoryCorps
- Verdienmodel: € 1.500 - € 9.500/jaar/tenant (zie spec §14.2) financiert verdere ontwikkeling
- Up-sell potentieel: alle SanskritiSetu enterprise-features (Canvas, AI-agents, Analytics) zijn direct te commercialiseren via de centrale console
- AI-tagging suggesties verlagen curator-tijd per item significant (geschat 60% reductie t.o.v. handmatige tagging)

### Negatief

- Twee deployments te onderhouden (SanskritiSetu backend + Next.js portal)
- Custom-domain support (fase 2) vereist DB-lookup per request → Redis-cache met TTL 60s, invalidatie via PUB/SUB bij `Tenant.domain` wijziging
- Wildcard TLS (fase 2) vereist DNS-API-toegang voor dnsChallenge
- AI-tagging kwaliteit voor NL historische teksten onbewezen → curator-validatie altijd verplicht
- Magic-link e-mail deliverability is single point of failure → SPF/DKIM/DMARC correct + monitoring vereist
- Eén Next.js deployment = single failure domain voor alle tenants; mitigatie via Azure Container App health probes + automatische restart
- `ContentTag` zonder eigen `tenant_id` is een afwijking van het standaardpatroon; documentatie + isolation-test cruciaal om regressie te voorkomen

### Resolved open issues (was: open in Proposed v0.1)

- **Vendor lock-in Ollama**: opgelost via `FailoverLLMProvider` (ADR-026) — primary
  Ollama, fallback OpenAI met `CircuitBreakerRegistry` per provider-positie.
  Wrapper-interface in `foundation_ai_tagging_service.py` abstraheert de
  concrete provider.

- **Pre-curatie LLM-moderation**: optional `moderation_score` veld op
  `FoundationContent` (0.0-1.0). MVP: niet auto-block; curator-UI toont
  score als badge. Post-MVP: bij score ≥ 0.90 auto-flag en escalatie naar
  senior curator. Threshold configureerbaar per tenant via `FoundationPortalSettings`.

- **Custom-domain caching strategy**: Redis-cache met TTL 60s, key
  `tenant:domain:{normalized_domain}`. Invalidatie via PUB/SUB op
  `tenant:domain:changed`. Bij cache-miss: DB-lookup met
  `SELECT tenant_id FROM tenants WHERE custom_domain=$1 AND is_active=true`.
  Bij DB-miss: 404 zonder onderscheid (anti-enumeratie). Implementatie in
  Fase 2 sub-plan.

- **Stripe webhook security** (post-MVP): HMAC-SHA256 signature
  verify met `STRIPE_WEBHOOK_SECRET` (rotated quarterly); idempotency-key
  per event-id in `stripe_webhook_events` tabel (TTL 30 dagen);
  retry-tolerant met `ON CONFLICT DO NOTHING`. Webhook endpoint zit
  achter eigen rate-limiter (`stripe_webhook_limit = 100/min`) en
  bewust NIET in `PUBLIC_PREFIXES` zodat de bestaande security-stack
  ervoor staat. Detail-spec in Fase 6 sub-plan.

### Resterende open issues (te beslissen vóór go-live)

- **Custom-domain TLS in fase 2**: dnsChallenge vereist DNS-API toegang
  per stichting OF één centrale wildcard `*.levend-monument.nl` + per-tenant
  CNAME. Voorkeur: wildcard + CNAME (minder DNS-bewerkingen voor klant).
- **Brevo deliverability monitoring**: bounce-rate threshold + alert. Open:
  bij welke bounce-rate (> 5%? > 10%?) we automatisch e-mail-verzending
  pauzeren per tenant.
- **AI-tagging kwaliteit-meting**: hoe meten we accuracy zonder
  ground-truth? Voorstel: curator-acceptance-rate per tag-type als proxy;
  drempel ≥ 70% acceptance per kwartaal anders prompt-tuning.

## Migration & deployment plan

### Fase 1 (week 5-12) — Backend Foundations

Detail-plan: `docs/superpowers/plans/2026-04-26-levend-monument-foundation-portal-plan.md`

- 7 modellen + 5 Alembic-migraties (registratie via `src/core/database/model_registry.py`)
- Slug-validatie consolideren: 3 bestaande `validate_slug` implementaties
  (`schemas/validators.py`, `api/v1/tenants/schemas.py`, `security/api_validation.py`)
  worden gereduceerd tot 1 canonical met optionele `reserved`-parameter +
  `FOUNDATION_RESERVED_SLUGS` frozenset
- Foundation-exceptions erven van `SanskritiError` (NIET `SanskritiSetuException` — dat bestaat niet)
- 6 rate-limiter wrappers via bestaande `privacy_rate_limit(max_requests, window_seconds, key_func)`
  pattern uit `src/core/governance/rate_limiter.py` (geen slowapi, geen tweede systeem)
- Tenant-resolver `public_tenant_scope` met `ContextVar` cleanup-garantie
- Cross-tenant isolation testsuite voor alle 7 modellen

**Go/no-go criterium**: alle isolation-tests groen + Alembic chain single-head
+ alle 3 originele `validate_slug` callers groen na consolidatie.

### Fase 2 (week 7-10) — Backend Services

- Azure Blob storage met magic-bytes MIME
- Ollama AI-tagging via Dramatiq
- Magic-link auth + Brevo client
- DSAR export

### Fase 3 (week 9-12) — Backend API

- Alle public + admin endpoints
- Audit-log integratie via `best_effort`

### Fase 4 (week 9-18, parallel met 3) — Next.js portal

- Aparte MIT-repo
- 14 pagina's met WCAG 2.1 AA

### Fase 5 (week 17-26) — Security & content & launch

- Pentest + WCAG-audit + remediation
- Co-creatie workshop
- Eerste 5 items uploaden
- MIT-release v1.0.0

### Rollback strategy

- **Code rollback**: revert PR + Alembic downgrade (per migratie 1 stap terug, in omgekeerde FK-volgorde).
- **Data rollback**: Azure Backup Vault dagelijkse PostgreSQL snapshot,
  RPO 24h. Blob versioning + soft-delete (30 dagen) voor content.
- **DNS rollback**: subdomain CNAME terug naar `_dead.levend-monument.nl`
  zodat de oude content niet meer bereikbaar is en de zoekmachine de
  pagina niet als 404 indexeert.

## SUMS-conformiteit (Cat 2, BWBR0049978)

| Aspect | Vastlegging |
|---|---|
| Projectnummer | 2025SUMSNL202137 |
| Beschikkingsdatum | 21-04-2026 |
| Projectperiode | 16-04-2026 t/m 15-04-2027 |
| Subsidie totaal | € 23.719 (€ 19.625 activiteiten + € 1.000 subsidie-advies-opslag + € 3.094 overhead 15%) |
| Verleningsvoorschot | 100% binnen 6 weken na 21-04-2026 |
| Toegekende activiteits-types | C (delen geschiedenis), F (digitaal platform), G (kunstuitingen) |
| Uitvoeringsmodel | Externe freelancers + dienstverleners conform begroting |
| Externe tarieven | € 25–€ 90/uur (alle onder Art 9 lid 4 grens van € 135/uur) |
| 3-offertes-eis (Art 9 lid 3) | Niet van toepassing — geen externe opdracht ≥ € 50.000 |
| Belangenconflict-clausule (Art 9 lid 5) | Niet van toepassing — geen interne uitvoering |
| Vrijwilligersovereenkomst (Art 16 lid 1) | Niet van toepassing — geen vrijwilligers in scope |
| Urenadministratie (Art 16 lid 2) | Verplicht per freelancer |
| Niet-subsidiabele kostenposten (Art 9 lid 6) | Hosting € 1.410 als dienst geboekt (niet licentie) |
| Open dossier (Art 11 lid 6) | Spec, ADR, runbooks zonder personalia |
| Meldingsplicht-drempels (Kaderbesluit 16 lid 3 sub a) | > 10% of > € 1.500 per categorie A-G |
| Steekproef-paraatheid (Kaderbesluit 16 lid 3 sub b) | DVO + offerte + uren + factuur + betaalbewijs + oplevering per activiteit |
| Ambtshalve vaststelling | Binnen 22 weken na 15-04-2027 (uiterlijk 16-09-2027) |

Volledige conformiteit-matrix in spec §14.7.

## Testing strategy

| Laag | Coverage-doel | Tools | Run-frequentie |
|---|---|---|---|
| Unit (models, validators, resolvers) | ≥ 95% per nieuw bestand | pytest + pytest-cov | Per push |
| Integration (Alembic chain, DB roundtrip) | Single-head + cyclic upgrade/downgrade | pytest `-m integration` + pgvector image | Per push |
| Security (cross-tenant isolation, 7 modellen) | 100% modellen covered | pytest `-m "security and multi_tenant"` | Per push (verplicht) |
| Chaos (timeout, broker-down) | Fase 2+ | pytest `-m chaos` | Pre-release |
| E2E (frontend + backend) | Alle 14 portal-pages | Playwright + axe-core | Per PR + nightly |
| Load (concurrent users) | 500/tenant gevalideerd | k6 | Pre-release |
| Pentest extern | Geen Critical/High open | Externe vendor (zie SOW spec §15.5) | Pre-launch |
| WCAG audit extern | AA op alle pages | Accessibility Foundation of equivalent | Pre-launch |

## Operational considerations

### Monitoring (OpenTelemetry, ADR-014)

Nieuwe metrics:
- `foundation_content_uploaded_total{tenant_slug,content_type}`
- `foundation_content_approval_duration_seconds{tenant_slug}` (histogram)
- `foundation_ai_tag_confidence{tenant_slug,tag_type}` (histogram)
- `foundation_ai_tag_duration_seconds{tenant_slug}` (histogram)
- `foundation_magic_link_requested_total{tenant_slug,outcome}`
- `foundation_takedown_open{tenant_slug}` (gauge — alert > 0 voor > 7 dagen)
- `foundation_newsletter_subscribers{tenant_slug,status}` (gauge)

Nieuwe trace-spans:
- `foundation.resolve_tenant_by_slug` (parent span van alle public requests)
- `foundation.ai_tag_dramatiq` (Dramatiq worker spans)
- `foundation.blob_upload`

Alerts:
- `foundation_takedown_open > 0 for 7d` → PagerDuty (curator-escalatie)
- `foundation_magic_link_requested_total{outcome="bounce"} rate > 5%` over 1h → Slack-channel (Brevo deliverability)
- `foundation_ai_tag_duration_seconds p95 > 60s` over 15min → Slack (Ollama health)

### Runbooks (zie `docs/runbooks/foundation-portal/`)

- `onboard-tenant.md` — nieuwe stichting toevoegen (slug-creatie, DNS, eerste curator)
- `revoke-tenant.md` — stichting offboarden (soft-delete, audit-export)
- `incident-magic-link-bounce.md` — wat te doen bij hoge bounce-rate
- `incident-cross-tenant-leak.md` — escalatie bij vermoeden van isolation-bug
- `restore-content.md` — soft-delete restoren uit Blob versioning
- `rotate-secrets.md` — BREVO_API_KEY, HCAPTCHA_SECRET, STRIPE_WEBHOOK_SECRET rotation

## Implementation

Detail-spec: [`docs/superpowers/specs/2026-04-26-levend-monument-foundation-portal-design.md`](../superpowers/specs/2026-04-26-levend-monument-foundation-portal-design.md)

Implementatie-plan Fase 1: [`docs/superpowers/plans/2026-04-26-levend-monument-foundation-portal-plan.md`](../superpowers/plans/2026-04-26-levend-monument-foundation-portal-plan.md)

Sub-plans Fase 2-6: te genereren via `superpowers:writing-plans` skill bij start van elke fase.

Runbooks: `docs/runbooks/foundation-portal/`

## References

- SUMS Categorie 2 regeling: BWBR0049978
- Dutch host-aansprakelijkheid: art. 6:196c BW (NTD-procedure)
- WCAG 2.1 AA: https://www.w3.org/TR/WCAG21/
- Creative Commons BY-NC-SA 4.0: https://creativecommons.org/licenses/by-nc-sa/4.0/
- STRIDE threat model: Microsoft SDL
- Brevo Transactional API: https://developers.brevo.com/
- Ollama OpenAI-compatible API: https://github.com/ollama/ollama
- Stripe Webhook Signing: https://docs.stripe.com/webhooks/signatures
- hCaptcha v3 score model: https://docs.hcaptcha.com/score
- Next.js App Router ISR: https://nextjs.org/docs/app/building-your-application/data-fetching/incremental-static-regeneration

## Changelog

- **2026-04-26 v0.1** — Initial Proposed (Rakesh)
- **2026-05-23 v0.2** — Major expansion: architectuur-diagrammen,
  sequence flows (magic-link, upload+AI, tenant resolution, NTD takedown,
  Stripe upgrade), NFRs met meetbare doelen, security threat model
  (STRIDE-light, 15 dreigingen), caching architectuur, rate-limit policy
  tabel, alle 4 open issues geresolveerd (Ollama failover, moderation,
  custom-domain cache, Stripe webhook security), testing strategy,
  operational considerations met OTel-metrics en runbook-lijst,
  rollback strategy.
- **2026-05-23 v0.3** — Codebase-alignment fixes na verificatie:
  Tier-namen corrigeren naar `FREE`/`STARTER`/`PRO`/`ENTERPRISE` zoals
  in `src/core/feature_flags/features.py` (was: "Professional"); Fase 1
  scope uitbreiden met `validate_slug` consolidatie (3 bestaande
  implementaties → 1 canonical); `FoundationError` erft van
  `SanskritiError` (was: niet-bestaande `SanskritiSetuException`);
  6 rate-limiter wrappers gebruiken bestaande `privacy_rate_limit`
  decorator-factory (was: slowapi-style die hier niet bestaat);
  modellen registreren via `src/core/database/model_registry.py`
  `_MODEL_GROUPS` tabel (was: directe import in `alembic/env.py`);
  `Base` import-pad correctie naar `src.core.database.database`
  (was: `src.core.models.base` dat niet bestaat).
- **2026-05-24 v0.4** — Cat 3 & Cat 4 subsidie-uitbreidingen:
  educatieve leeromgeving met access-code flow (geen leerling-accounts),
  kaartweergave met lat/lon + MapLibre, polymorfe content-types,
  OAI-PMH metadata-export, school/docententoegang, geo-isolatie-
  vereisten, bijbehorende NFRs en datamodel-uitbreidingen.
