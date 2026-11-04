# ADR-029: Status & Vervolg — Samenvattend Werkdocument

**Datum:** 2026-09-09
**Status van dit document:** HET actuele overzicht voor ADR-029 (Foundation Portal / Levend Monument).
**Vervangt niks:** het gedetailleerde implementatieplan blijft `029-gap-analysis-productieklaar-rapport.md` (2026-08-30); dit document bundelt status, historische context, het herstelde prototype en de open beslissingen op één plek.

---

## 1. Huidige status (geverifieerd 2026-09-09)

### WEL klaar

| Onderdeel | Status |
|---|---|
| Data-laag: 9 modellen + 8 enums | 100% — `src/core/models/foundation_content.py` |
| Foundation router (7 sub-routers) | ~90% — `src/core/api/v1/foundation/` |
| Magic-link auth (aanvraag + verificatie) | 100% — `auth.py` |
| Tenant resolver + ContextVar-cleanup | 100% |
| Rate limiters + JWT portal-dependencies | 100% |
| Migraties incl. v1-uitbreiding | 100% — `20260824_adr029_portal_v1.py` |
| `metadata_` SQLAlchemy-collision fix | 100% — commit `ad345be8` |
| Unit- + RLS-security-tests | 100% groen — alle 8 Foundation-tabellen getest incl. educational_access en study_collections |
| Upload-endpoint + storage-service | 100% — BE-EP-036 (2026-09-09), incl. rate limiter op create_content (N-4) |
| Kaart/geo-endpoint | 100% — BE-EP-037 (2026-09-09), GeoJSON bbox-endpoint met anti-scrape span-cap |
| Educatieve leeromgeving (`/edu/*`) | 100% — BE-EP-039 (2026-09-10), opaak sessie-ID in Redis (TTL 4u), DB-hervalidatie per request, O5 visibility-filter |
| OAI-PMH metadata harvest endpoint | 100% — BE-EP-040 (2026-09-10), OAI-PMH v2.0 protocolconform (6 verbs, XML text/xml, HTTP 200 error tags, keyset resumptionToken HMAC-signed, N-2 invariant, anonimiteitsmaskering) |
| AI Content Tagging & Background Worker | 100% — BE-EP-041 / BE-SVC-018 (2026-09-10), NDE taxonomie tagging, Dramatiq worker `tag_foundation_content_async`, curator re-tag endpoint |

### NOG OPEN — P0 (blokkerend voor productie)

| # | Gap | Kern |
|---|---|---|
| P0-1 | Ontbrekende tabellen in migraties | `portal_users`, `magic_link_tokens`, `takedown_requests`, `newsletter_subscriptions` worden nooit aangemaakt |
| P0-7 | Geen frontend | zie sectie 3 |

P0-2 (RLS) is op 2026-09-10 formeel afgerond: alle 8 Foundation-tabellen (inclusief `educational_access` en `study_collections`) zijn voorzien van integratietests tegen echte PostgreSQL RLS en 100% groen.

P0-3 is op 2026-09-09 opgeleverd (BE-EP-036, APPROVED): `POST /{tenantSlug}/foundation/content/{content_id}/upload` + `FoundationStorageService` (local/azure). Open opvolgpunten uit de review (LOW): in-memory rate limiter per worker, `secure_filename("..")`, 503-test, pin-stijl. Acceptatiecriterium voor het toekomstige serveer-endpoint (P1): read-SAS op serve-moment (bij voorkeur user-delegation), container moet private blijven, polyglot-bestanden-serveren afdekken.

P0-4 is op 2026-09-09 opgeleverd (BE-EP-037, APPROVED): publiek `GET /{tenantSlug}/foundation/map/bbox` als GeoJSON, alleen APPROVED+PUBLIC, span-cap 2.0 graden + cap 500 + `has_more`. Opvolgpunt uit die review is dezelfde dag opgelost: **BE-EP-038 (APPROVED)** laat alle publieke serializers (content list + detail + map) `creator_name` maskeren bij `is_anonymous=True` via een gedeelde helper; de curatie-queue behoudt bewust de naam (moderatie). Nog open (LOW/MEDIUM): naam kan lekken via vrije velden (`metadata_`/`title_nl`/`body` — productbeslissing/UI-communicatie), substring-matching in `public_registry.py`, lichte contract-test voor toekomstige serializers, `has_more`-contract verifiëren bij P0-7.

P0-5 is op 2026-09-10 opgeleverd (BE-EP-039, APPROVED): 5 endpoints in `edu.py` (POST/GET/DELETE session, GET edu content list/detail) + `EduSessionService` (opaak 256-bit sessie-ID, Redis TTL 14.400s, DB-hervalidatie per request tegen PostgreSQL). N-2 invariant bewezen via O5 visibility-filter in `content.py` (edu-content onzichtbaar in publieke archief). Open opvolgpunten uit de review (MEDIUM/LOW): school-NAT burst rate-limiter, salt toevoegen aan code-hash bij code-aanmaak feature, delete-cookie secure-flag.

P0-6 is op 2026-09-10 opgeleverd (BE-EP-040, APPROVED): OAI-PMH v2.0 endpoint op `/{tenantSlug}/foundation/oai-pmh` (GET en POST), dwingend XML response format (`text/xml`), protocol error handling via HTTP 200 met `<error code="...">`, alle 6 verbs (Identify, ListMetadataFormats, ListSets, GetRecord, ListIdentifiers, ListRecords), stateless HMAC-SHA256 signed keyset resumptionToken met exclusiviteits-guard, N-2 invariant (edu/community uitgesloten) en Dublin Core anonimiteitsmaskering (BE-EP-038). Open opvolgpunten uit de review (MEDIUM/LOW): pure keyset-paginatie (zonder OFFSET) bij hele grote collecties, 503 Retry-After rate limiting voor harvesters.

P1-1 is op 2026-09-10 opgeleverd (BE-EP-041 / BE-SVC-018, APPROVED): AI content tagging service over NDE-thematiek (5 tagtypes), Dramatiq background worker (`tag_foundation_content_async`), curator re-tag endpoint (`POST /admin/curatie/{content_id}/re-tag`), selectinload eager loading en TypedDict typing.

P1 (overig): content PUT/DELETE, hCaptcha, Azure Blob service, Brevo client, integratietests voor endpoints.
P2 (post-MVP): custom domain, Stripe tiers, analytics, WCAG 2.1 AA-audit.

Detail + uitwerking per gap: **zie `029-gap-analysis-productieklaar-rapport.md`**.

---

## 2. Historische context (waarom dit document er ligt)

In de chatsessie **"ADR 029 Status en Impact"** (2026-06-09, vervolgaudit 2026-06-13) is ADR-029 voor het eerst volledig in kaart gebracht. Die sessie concludeerde destijds:

- ADR-029 was **~20% compleet** (alleen de data-laag).
- Advies: bouw de API-laag volgens het `src/core/api/v1/foundation/` patroon, begin met gateway + dependencies (import-linter Contract 1), en start een apart frontend-project.

**Wat is sindsdien veranderd:** dat advies is opgevolgd. De foundation-router, magic-link auth en de v1-migratie zijn inmiddels gebouwd — de codebase is van ~20% naar "Fase 1 af, Fase 2/3 deels" gegaan. De architectuurkeuzes uit juni zijn dus consistent gebleken en gelden ongewijzigd.

Bronnen (in deze repo):
- `docs/adr/029-chatsessie-2026-06-09-transcript.txt` — volledige transcriptie van de sessie.
- `docs/adr/029-historische-audit-2026-06-13.md` — het auditrapport van juni.

---

## 3. Hersteld frontend-prototype (referentie)

De eerder gepubliceerde site **Levend Monument Portal** (live gezet in een eerdere iteratie, bron was kwijt) is op 2026-09-09 volledig hersteld van de publicatie-URL en ligt nu in:

```
prototype/levend-monument-portal/
```

**Techniek:** React 18 + **Vite** (geen Next.js), kaart via **MapLibre GL JS 4.7.1** — exact de bibliotheek die ADR-029 voorschrijft.
**Inhoud:** 13 schermen (ontdekken, kaart, item-detail, uploaden "Deel je Verhaal", educatie, docenten, inloggen, beheer, nieuwsbrief, contact, data-export), 16 afbeeldingen, Nederlandse teksten.

**Twee eerlijke kanttekeningen:**
1. Het is een **frontend-demo zonder backend** — gegevens verdwijnen bij verversen; koppeling aan deze backend moet nog.
2. De code is **gemalen (minified)**; de nette bron is niet meer te herleiden. Gebruik het als visueel/Functioneel einddoel; herbouw de code netjes in het echte frontend-project.

---

## 4. Open beslissingen (wachten op Rakesh)

| # | Beslissing | Vraag |
|---|---|---|
| D1 | **Frontend-framework** | Vite (eenvoud, prototype past hierbij) of Next.js (SEO/vindbaarheid publiek erfgoedarchief)? Dit blokkeert P0-7. |
| D2 | Brevo bounce-drempel | Waarde vastleggen voor mail-aflevermonitoring. |
| D3 | OP-149 | DROP-GO beslissing (verwijderen of doorontwikkelen). |
| D4 | LandingPage-testfix | GO om de outdated frontend-test aan te passen (CTASection >=3 i.p.v. >=4, bewuste wijziging sinds ADR-036 OP-137). |

---

## 5. Harde werklocatie-regel (2026-09-09, door Rakesh bepaald)

**Vanaf 2026-09-09 wordt UITSLUITEND gewerkt in deze repository (`het-levend-monument`).**
De repository `RakeshRamkhelawan/SanskritiSetu.org` wordt **nooit** aangepast, gepusht of gesynchroniseerd, **tenzij Rakesh dat expliciet in eigen woorden opdracht geeft** in de betreffende sessie.

Toegestaan zonder extra toestemming: lezen van de lokale SanskritiSetu-map als naslag.
Niet toegestaan zonder expliciete opdracht: commits, pushes, merges, branch-wijzigingen, remote-wijzigingen, deploys — naar of vanuit SanskritiSetu.

Deze regel staat ook bovenaan in `CLAUDE.md` zodat elke toekomstige sessie hem als eerste tegenkomt.
