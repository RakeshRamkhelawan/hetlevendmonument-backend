# Review BE-EP-022: Foundation Portal Content Endpoints

**Reviewer-prompt:** Officiele reviewer-prompt uit FEATURE_DOC_WORKFLOW.md
**Datum:** 2026-08-24
**Bijgewerkt:** 2026-08-25 -- C-001 en C-002 opgelost, zie "Wat is opgelost" bij elke bevinding hieronder en de sectie "Beslissing"
**Review door:** Auto-review (onafhankelijke gap-analyse)
**Feature ID:** BE-EP-022
**Status:** APPROVED WITH MINOR GAPS

---

## Overzicht

| Categorie | Aantal | Opgelost (2026-08-25) |
|-----------|--------|------------------------|
| CRITICAL | 2 | 2 (C-001, C-002) |
| HIGH | 4 | 0 |
| MEDIUM | 5 | 0 |
| LOW | 2 | 0 (L-001 deels, alleen create-request veldnaam) |
| Goed nieuws | 4 | -- |

---

## CRITICAL

### [C-001] ID-conflict: BE-EP-001 bestaat al -- OPGELOST 2026-08-25

**Sectie:** Metadata, bestandsnaam
**Probleem:** De feature ID `BE-EP-001` is al toegewezen aan "Pack Feedback API Endpoints" (`docs/backend/features/BE-EP-001-pack-feedback-endpoints.md`, geregistreerd in ID-REGISTRY.md, datum 2026-05-28). Het toewijzen van hetzelfde ID aan twee verschillende features breekt de uniekheid van het ID-register en maakt traceerbaarheid onmogelijk.
**Waarom dit een probleem is:** Zoekopdrachten, CI-scripts, en sprint-tracking verwachten dat elke ID uniek is. Dubbele IDs leiden tot verwarring bij code reviews, audit-trails, en LLM-training data.
**Concrete correctie:** Wijs een nieuw uniek ID toe. Aanbevolen: `BE-EP-022` (volgende vrije nummer in de reeks, na BE-EP-021). Hernoem bestand naar `BE-EP-022-foundation-content-endpoints.md` en update het ID-register.
**Wat is opgelost:** Metadata `Feature ID` in de spec gewijzigd van `BE-EP-001` naar `BE-EP-022` (matcht de bestandsnaam, die al `BE-EP-022-foundation-content-endpoints.md` was). Geen nieuw ID verzonnen: ID-REGISTRY.md had op regel 517 al een `BE-EP-022`-rij staan, gereserveerd op 2026-07-27 voor exact dezelfde feature ("Foundation Content CRUD -- GET lijst, GET detail, POST upload"), maar wees naar een bestand dat nooit heeft bestaan (`BE-EP-029-001-foundation-content-crud.md`, bevestigd via `git log --all` op dat pad -- geen resultaten). Die orphaned registry-rij is nu bijgewerkt om naar het echte bestand te verwijzen. `BE-EP-001` blijft ongewijzigd toegewezen aan Pack Feedback.

### [C-002] FastAPI route + file upload + JSON body onmogelijk -- OPGELOST 2026-08-25

**Sectie:** 8. Request-specificatie -- POST endpoint, 6. Technische beschrijving
**Probleem:** De spec definieert `FoundationContentCreate` als JSON body met velden zoals `type`, `title_nl`, etc., EN een `file: UploadFile | None` in hetzelfde request body. FastAPI ondersteunt geen native combinatie van JSON body + `UploadFile` in dezelfde endpoint. De enige werkbare patronen zijn: (a) multipart form-data voor ALLE velden, of (b) file upload als aparte endpoint gevolgd door metadata update, of (c) base64-encoded file in JSON body.
**Waarom dit een probleem is:** Deze spec is niet implementeerbaar zoals beschreven. Een ontwikkelaar die dit volgt loopt direct tegen een FastAPI beperking aan.
**Concrete correctie:** Kies expliciet een van deze drie patronen en documenteer:
- Optie A (aanbevolen): `FoundationContentCreate` wordt een multipart form-data schema waarbij alle velden form-fields zijn en `file` een UploadFile. Voorbeeld: `@router.post(...)` met `type: ContentType = Form(...)`, `title_nl: str = Form(...)`.
- Optie B: Twee-fase upload: eerst `POST /content` met JSON metadata (retourneert content_id), daarna `POST /content/{id}/file` met UploadFile.
- Optie C: File als base64 string in JSON body (niet aanbevolen voor grote bestanden).
**Wat is opgelost:** De ECHTE, geshipte code (`src/core/api/v1/foundation/content.py::create_content`, regel 131-170) had dit probleem nooit -- de endpoint neemt uitsluitend `data: FoundationContentCreateRequest` (een Pydantic JSON-body), zonder `UploadFile`-parameter. De code was dus nooit fout; alleen de spec beschreef een aspirationeel multipart/UploadFile-ontwerp dat nooit is geimplementeerd (vermoedelijk precies omdat het tegen deze FastAPI-beperking aanliep). De spec is gecorrigeerd om de echte, JSON-only endpoint te beschrijven: alle multipart/`UploadFile`-vermeldingen zijn verwijderd of herschreven (secties 6, 8, 9 t/m 11, 13, 17-19, curl-voorbeeld, open aannames/vragen/risico's), de schema-klasse is hernoemd naar de echte naam `FoundationContentCreateRequest`, het veld `metadata_` in de create-request is gecorrigeerd naar de echte veldnaam `metadata`, en er is expliciet vastgelegd dat deze endpoint vandaag geen file-upload capability heeft -- media wordt uitsluitend via het `external_url` tekstveld gerefereerd (geverifieerd tegen `src/core/api/v1/foundation/schemas.py`). Bijvangst: bij het corrigeren bleek dat de spec ook een niet-bestaande `@model_validator` claimde (afdwingen van `rights_confirmed=True` en "file of external_url"); `schemas.py` bevat geen zulke validator, dus die claims zijn eveneens gecorrigeerd naar de feitelijke situatie (geen server-side cross-field enforcement).

---

## HIGH

### [H-001] Tenant claim validatie in require_portal_user ontbreekt

**Sectie:** 6. Technische beschrijving (dependencies), [BE-DEP-029-001]
**Probleem:** De `require_portal_user` dependency valideert het JWT token maar er staat geen beschrijving van hoe de tenant uit de URL slug wordt gekoppeld aan de `tenant_id` claim in het JWT. Een user met een geldig token voor tenant A zou theoretisch requests kunnen sturen naar tenant B's endpoints.
**Waarom dit een probleem is:** Dit is een cross-tenant autorisatiegat. Zonder expliciete tenant claim validatie is de security afhankelijk van de aanname dat het token alleen voor de juiste tenant werkt.
**Concrete correctie:** Voeg toe aan `require_portal_user`: na JWT decode, vergelijk `token.tenant_id` met de `tenant_id` uit `public_tenant_scope`. Bij mismatch: 403 Forbidden. Documenteer dit expliciet in de spec.

### [H-002] Privacy filter (COMMUNITY vs PUBLIC) niet uitgewerkt

**Sectie:** 5. Functionele beschrijving, 11. Business rules, 17. Acceptatiecriteria
**Probleem:** De spec stelt dat "Community privacy content alleen zichtbaar is voor ingelogde users" maar beschrijft niet hoe dit in de `GET /content` list endpoint wordt afgedwongen. Moet de lijst endpoint een optionele auth dependency hebben? Of worden COMMUNITY items uitgesloten voor anonieme requests? Hoe wordt dit onderscheid gemaakt?
**Waarom dit een probleem is:** De acceptatiecriteria vereisen dit gedrag maar de technische beschrijving en request-specificatie geven geen richting voor implementatie.
**Concrete correctie:** Documenteer expliciet:
- Anonieme requests: WHERE `privacy = PUBLIC` AND `status = APPROVED`
- Geauthenticeerde requests: WHERE (`privacy = PUBLIC` OR `privacy = COMMUNITY`) AND `status = APPROVED`
- Voeg een optionele auth dependency toe aan de list endpoint: `current_user: PortalUser | None = Depends(get_optional_portal_user)`

### [H-003] ContentTag JOIN query niet beschreven

**Sectie:** 6. Technische beschrijving, 3. Gerelateerde flow (BE-FLW-029-003)
**Probleem:** De spec noemt dat tags worden eager-loaded via `selectinload`, maar `ContentTag` heeft geen eigen `tenant_id` (ADR-029 uitzondering). De spec beschrijft niet hoe de JOIN query eruitziet en hoe wordt gegarandeerd dat tags van andere tenants niet worden meegeladen.
**Waarom dit een probleem is:** De AGENTS.md waarschuwt expliciet: "Queries op ContentTag MOETEN altijd via JOIN of subquery op FoundationContent.id lopen." Als een ontwikkelaar `select(ContentTag)` doet zonder JOIN, bypass dit de RLS isolatie.
**Concrete correctie:** Documenteer de exacte query:
```python
select(FoundationContent)
.options(selectinload(FoundationContent.tags))
.where(FoundationContent.status == ContentStatus.APPROVED)
```
De `do_orm_execute` hook filtert `FoundationContent` op tenant_id; de `selectinload` laadt alleen gerelateerde `ContentTag` rijen die gekoppeld zijn aan gefilterde content. Voeg een code-voorbeeld toe.

### [H-004] Pydantic schema code ontbreekt

**Sectie:** [BE-SCH-029-001], [BE-SCH-029-002], [BE-SCH-029-003]
**Probleem:** De spec beschrijft schema velden in natuurlijke taal maar bevat geen concrete Pydantic model definities (class statements, Field constraints, ConfigDict). Voor een implementatie-spec is dit te vaag.
**Waarom dit een probleem is:** Ontwikkelaars moeten raden welke types, defaults, en validators te gebruiken. Dit leidt tot inconsistente implementaties.
**Concrete correctie:** Voeg complete Pydantic model code toe aan de schema secties, inclusief:
```python
class FoundationContentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    type: ContentType
    title_nl: str = Field(..., min_length=1, max_length=255)
    # ... etc
```

---

## MEDIUM

### [M-001] Rate limit decorator volgorde niet gespecificeerd

**Sectie:** 6. Technische beschrijving, 8. Request-specificatie
**Probleem:** De spec noemt dat decorators worden gebruikt (`portal_public_read_limit`, `portal_public_write_limit`) maar beschrijft niet de decorator volgorde. In FastAPI moet de rate limit decorator NA de route decorator komen: `@router.get(...)` eerst, dan `@portal_public_read_limit`.
**Waarom dit een probleem is:** Verkeerde decorator volgorde kan leiden tot stilzwijgend falen van rate limiting.
**Concrete correctie:** Voeg expliciet toe: "Decorator volgorde: `@router.get(...)` bovenaan, `@portal_public_read_limit` er direct onder."

### [M-002] Upload response contradictie

**Sectie:** 9. Response-specificatie -- POST
**Probleem:** De spec zegt dat POST 201 retourneert met `FoundationContentDetailResponse` (de wrapper met `{"success": true, "data": {...}}`), maar in de codebase wordt voor 201 responses vaak alleen de data object teruggegeven zonder wrapper. De spec is hier inconsistent met het pack-feedback pattern (200 met wrapper) zonder uitleg.
**Waarom dit een probleem is:** Frontend moet weten of het `response.data.id` of `response.id` moet gebruiken.
**Concrete correctie:** Beslis expliciet: gebruik `{"success": true, "data": {...}}` wrapper voor ALLE responses (consistent met pack feedback), of gebruik alleen het data object voor 201. Documenteer de keuze.

### [M-003] Full-text search implementatie vaag

**Sectie:** 8. Request-specificatie -- GET list, 6. Technische beschrijving
**Probleem:** De spec noemt een `q` parameter voor full-text search maar beschrijft niet hoe dit geimplementeerd wordt (ILIKE per kolom? PostgreSQL tsvector? BM25 hybrid search?).
**Waarom dit een probleem is:** Performance en zoekkwaliteit hangen sterk af van de gekozen implementatie.
**Concrete correctie:** Documenteer de MVP implementatie: `ILIKE` op `title_nl`, `title_en`, `description_nl`, `description_en`, `body_nl`, `body_en`. Post-MVP: overweeg `pg_trgm` of BM25 via bestaande hybrid search module.

### [M-004] Ontbrekende 410 Gone voor verwijderde content

**Sectie:** 13. Foutafhandeling
**Probleem:** De spec noemt 404 voor "niet gevonden of niet approved" maar niet 410 Gone voor content die eerst approved was maar nu removed (takedown). Het `ContentStatus` enum bevat `REMOVED`.
**Waarom dit een probleem is:** Een gebruiker die een oude bookmark volgt krijgt 404, wat ambigu is (nooit bestaan vs verwijderd).
**Concrete correctie:** Voeg toe: 404 voor onbekend/niet-bestaand content_id; 410 voor content met `status = REMOVED`.

### [M-005] `require_portal_user` heeft geen toegang tot URL path params

**Sectie:** [BE-DEP-029-001]
**Probleem:** FastAPI `Depends` functies hebben geen toegang tot path parameters (`tenantSlug`) tenzij expliciet `request: Request` wordt geinjecteerd. De spec beschrijft `require_portal_user` met alleen `authorization: str` en `session: AsyncSession`.
**Waarom dit een probleem is:** De tenant validatie (zie H-001) kan niet worden uitgevoerd zonder toegang tot de request of tenant context.
**Concrete correctie:** Voeg toe aan de dependency signature: `request: Request` parameter, of gebruik de bestaande ContextVar (`get_current_tenant_id()`) om de tenant op te halen.

---

## LOW

### [L-001] `metadata_` veldnaam inconsistentie

**Sectie:** 8. Request-specificatie, model beschrijving
**Probleem:** Het ORM model gebruikt `metadata_` (met underscore omdat `metadata` een SQLAlchemy reserved name is), maar de spec noemt `metadata_` in sommige plaatsen en `metadata` in andere.
**Waarom dit een probleem is:** Kleine inconsistentie die tot verwarring kan leiden bij API consumers.
**Concrete correctie:** Standaardiseer op `metadata` in het API contract (Pydantic schema) en `metadata_` alleen in het ORM model. Documenteer deze mapping expliciet.

### [L-002] Acceptatiecriteria tellen niet op

**Sectie:** 17. Acceptatiecriteria
**Probleem:** Er staan 17 acceptatiecriteria maar enkele zijn dubbelop of te breed. Bijvoorbeeld: "Tenant A kan nooit content van tenant B zien" en "Cross-tenant content invisible" zijn hetzelfde.
**Waarom dit een probleem is:** Lijst is minder overzichtelijk dan nodig.
**Concrete correctie:** Consolideer dubbele criteria. Splits te brede criteria op in testbare sub-criteria.

---

## Goed nieuws

- [G-001] Volledige architectuurbeschrijving met ADR-033 laag 1/2/3 router pattern.
- [G-002] Tenant isolatie goed beschreven via `public_tenant_scope()` + ContextVar + RLS.
- [G-003] Rate limiting is expliciet gekoppeld aan bestaande governance decorators.
- [G-004] Trainingssamenvatting aanwezig voor alle artefacten.

---

## Issue register

| Severity | ID | Sectie | Probleem | Waarom | Concrete correctie |
|----------|-----|--------|----------|--------|-------------------|
| CRITICAL | C-001 | Metadata | ID BE-EP-001 bestaat al als Pack Feedback | Traceerbaarheid breekt | Hernoem naar BE-EP-022, update register |
| CRITICAL | C-002 | POST endpoint | JSON body + UploadFile in zelfde endpoint | Niet implementeerbaar in FastAPI | Kies multipart-form of twee-fase upload |
| HIGH | H-001 | Dependencies | JWT tenant claim vs URL slug niet gevalideerd | Cross-tenant auth gat | Voeg tenant claim check toe aan dependency |
| HIGH | H-002 | List endpoint | Privacy filter niet uitgewerkt | COMMUNITY content lekt mogelijk | Documenteer WHERE clause per auth status |
| HIGH | H-003 | Detail endpoint | ContentTag JOIN query niet beschreven | RLS bypass risico | Documenteer exacte query met selectinload |
| HIGH | H-004 | Schema secties | Geen Pydantic model code | Implementatie onduidelijk | Voeg volledige class definities toe |
| MEDIUM | M-001 | Technisch | Decorator volgorde niet gespecificeerd | Rate limit werkt mogelijk niet | Documenteer @router.get boven @limit |
| MEDIUM | M-002 | POST response | 201 wrapper format inconsistent | Frontend verwarring | Beslis en documenteer wrapper keuze |
| MEDIUM | M-003 | GET list | Full-text search implementatie vaag | Performance onzeker | Documenteer ILIKE als MVP |
| MEDIUM | M-004 | Foutafhandeling | 410 Gone ontbreekt voor REMOVED | Ambigue 404 | Voeg 410 toe voor takedown content |
| MEDIUM | M-005 | Dependency | require_portal_user heeft geen request | Tenant validatie onmogelijk | Voeg Request parameter toe |
| LOW | L-001 | Schema | metadata vs metadata_ inconsistent | API verwarring | Standaardiseer op `metadata` in API |
| LOW | L-002 | Acceptatie | Dubbele criteria | Overzicht verminderd | Consolideer criteria |

---

## Ontbrekende items

1. **Upload file size limit:** Geen max file size gedefinieerd (alleen "TODO: 50MB" in aannames).
2. **Allowed MIME types lijst:** Geen concrete lijst van toegestane bestandstypen.
3. **File storage path format:** Geen beschrijving van hoe het lokale pad wordt opgebouwd.
4. **Content soft-delete:** Geen beschrijving van wat er gebeurt bij DELETE (indien toekomstig).
5. **OpenTelemetry span attributen:** Geen concrete attributen lijst.
6. **DB index usage:** Geen vermelding van welke indexen worden gebruikt voor de list query.

---

## Verbeterde tekstvoorstellen

### Huidig (C-002 impact):
```
Request body (schema): FoundationContentCreate
  - type: str (verplicht)
  - title_nl: str (verplicht, max 255)
  - file: UploadFile | None
```

### Voorgesteld:
```
Request body: multipart/form-data
  - type: str = Form(...) (verplicht, enum: story, artwork, audio, document, poetry, link)
  - title_nl: str = Form(..., min_length=1, max_length=255)
  - file: UploadFile | None = File(None) (optioneel, max 50MB)
  - external_url: str | None = Form(None)

Constraint: minstens een van file of external_url moet aanwezig zijn.
```

---

## Release-oordeel

| Criterium | Geschikt? |
|-----------|-----------|
| Bouw / implementatie | JA -- C-002 opgelost; spec beschrijft nu de echte, al geshipte JSON-only endpoint (geen FastAPI-constraint meer) |
| QA en geautomatiseerd testen | GEDEELDELIJK -- test cases zijn beschreven maar volledige Pydantic model code ontbreekt nog (H-004, open) |
| LLM-training | JA -- structuur en flows zijn goed beschreven |
| Integratorhandleiding / API-documentatie | JA -- integratoruitleg is helder en nu ook feitelijk correct (JSON i.p.v. multipart) |

---

## Beslissing

### APPROVED WITH MINOR GAPS

**Bijgewerkt 2026-08-25.** Beide CRITICAL blokkers zijn opgelost:

- **C-001 (ID-conflict):** opgelost -- Feature ID in de spec is BE-EP-022, matcht de bestandsnaam en vult de orphaned registry-rij in ID-REGISTRY.md.
- **C-002 (FastAPI JSON+UploadFile):** opgelost -- de spec is gecorrigeerd naar de echte, al geimplementeerde JSON-only endpoint. De code was nooit fout; alleen de spec beschreef een nooit-gebouwd multipart-ontwerp.

Met beide CRITICAL-blokkers weg is de spec bruikbaar voor implementatie/onboarding (de endpoint bestaat al en werkt zoals nu beschreven). De HIGH, MEDIUM en LOW bevindingen uit de oorspronkelijke review (H-001 t/m H-004, M-001 t/m M-005, L-001, L-002) zijn NIET onderdeel van deze correctieronde en blijven openstaand als documentatiegaten -- vandaar "MINOR GAPS" in plaats van volledig APPROVED. Zie de tabellen "HIGH", "MEDIUM", "LOW" en "Issue register" hierboven voor de volledige, ongewijzigde lijst.

### Openstaande gaps (niet opgelost in deze ronde)

1. H-001: tenant claim validatie in `require_portal_user` niet gedocumenteerd (de ECHTE code in `src/core/api/v1/foundation/dependencies.py` doet dit overigens al -- de spec documenteert het alleen nog niet)
2. H-002: privacy filter (COMMUNITY vs PUBLIC) niet uitgewerkt in de spec
3. H-003: ContentTag JOIN query niet beschreven
4. H-004: volledige Pydantic model code ontbreekt in schema secties
5. M-001 t/m M-005: zie MEDIUM-sectie hierboven
6. L-001: `metadata` vs `metadata_` inconsistentie -- deels verholpen (create-request veldnaam is nu correct `metadata`), maar de list/detail response-secties zijn niet aangepast
7. L-002: dubbele acceptatiecriteria niet geconsolideerd

---

*Review uitgevoerd conform FEATURE_DOC_WORKFLOW.md reviewer prompt*
*Template: docs/backend/FEATURE_DOC_WORKFLOW.md*
*C-001/C-002 verificatie: src/core/api/v1/foundation/content.py en schemas.py gelezen 2026-08-25; ID-REGISTRY.md regel 517 bijgewerkt.*
