# Backend Feature Specification

## Metadata

| Veld | Waarde |
|---|---|
| Feature ID | BE-EP-038 |
| Naam | is_anonymous platform-breed honoreren (privacy-fix, opvolger BE-EP-037 review) |
| Status | Approved (Gate 2 APPROVED ronde 1 + Gate 3 groen, 2026-09-09) |
| Auteur | Kimi agent (sessie 2026-09-09) |
| Reviewer | Onafhankelijke review-agent (Gate 2) |
| Datum | 2026-09-09 |
| User story / ticket | HIGH-bevinding uit `docs/backend/review/review-BE-EP-037.md` + bevestiging via code-lezing 2026-09-09: `is_anonymous=True` wordt buiten het map-endpoint nergens gehonoreerd |
| Router / module | `src/core/api/v1/foundation/schemas.py` (serialisatie) |
| Frontend endpoints | N.v.t. |
| Database tabellen | `foundation_contents` — geen wijziging, GEEN migratie |
| Versie | 1.0 |

---

## Doel en scope

### Doel

Een uploader die `is_anonymous` aanvinkt mag nergens via een publiek endpoint alsnog met naam zichtbaar worden. Vandaag lekken de publieke content-list (`GET /{tenantSlug}/foundation/content`) en content-detail (`GET /{tenantSlug}/foundation/content/{id}`) `creator_name` ook als `is_anonymous=True`. BE-EP-037 heeft dit alleen voor het map-endpoint gerepareerd; deze feature sluit de rest.

### In scope

- Maskering van `creator_name` in `FoundationContentListItem` en `FoundationContentDetail` als `is_anonymous=True`
- Een gedeelde maskeringshelper zodat de regel op precies een plek leeft
- Unit-tests (offline) + integratietests
- Documentatie van de bewuste uitzondering (curatie-queue)

### Out of scope

- `CuratieQueueItem` (admin/curatie): curatoren MODEREN content en moeten de indiener kunnen identificeren; maskeren daar zou de curatiewerkstroom breken. Bewuste uitzondering, gedocumenteerd.
- Map-endpoint (al gerepareerd in BE-EP-037)
- Wijzigingen aan upload/create-flow (die slaat de velden correct op)
- Migraties, modelwijzigingen

---

## Ontwerpbeslissingen (door de architect, met reden)

| # | Beslissing | Reden |
|---|---|---|
| O1 | **Een helper `apply_anonymity_mask(...)`** die vanuit beide schemas wordt aangeroepen | De regel "is_anonymous => creator_name is None" mag nooit op twee plekken gaan divergeren; een helper is de enige manier om dat structureel te borgen. |
| O2 | **Maskering in de Pydantic-schema's** (model_validator), niet in de endpoints | `get_content` retourneert het ORM-object direct en laat `response_model` serialiseren; `list_content` doet `model_validate`. Een validator op het schema dekt dus beide paden zonder endpoint-code te raken. |
| O3 | **`is_anonymous` blijft zichtbaar in de response** | De vlag zelf is geen geheim (de uploader koos hem); de frontend kan er "Anoniem" mee tonen. Alleen de naam wordt gemaskeerd (None). |
| O4 | **Curatie-queue behoudt de naam** | Curator is een vertrouwde rol binnen de tenant (auth vereist, require_curator). Moderatie zonder indiener-identiteit is onwerkbaar. Vastgelegd als bewuste uitzondering met risico-paragraaf. |
| O5 | **Geen wijziging aan opgeslagen data** | De naam blijft in de DB staan; dit is puur een serialisatieregel. Curatie en toekomstige admin-flows blijven mogelijk. |

---

## Build summary

### Nieuw gebouwd

- `tests/unit/test_be_ep_038_anonymous_masking_offline.py` — schema-validator tests zonder DB
- `tests/integration/api/v1/foundation/test_anonymous_masking.py` — end-to-end bewijs

### Gewijzigd

- `src/core/api/v1/foundation/schemas.py` — helper + validators op `FoundationContentListItem` en `FoundationContentDetail`
- `src/core/api/v1/foundation/map.py` — `content_to_feature` hergebruikt nu `apply_anonymity_mask` in plaats van de inline BE-EP-037-maskering (open LOW uit de Gate-2-review: een bron van waarheid, geen divergente regels)
- `docs/backend/features/ID-REGISTRY.md` — BE-EP-038

### Verwijderd

- Niets.

### Beinvloede bestaande flows

- Publieke list/detail: anonieme content toont voortaan `creator_name: null`. Bestaande tests die voor anonieme fixtures een naam verwachten moeten worden gecorrigeerd (dat is dan een test die het lek vastlegde, geen regressie).
- Curatie-queue: ongewijzigd.

---

## Detaildocumentatie

### Helper + validators

1. **Type:** serialisatie-logica (pure functie + Pydantic model_validators)
2. **Locatie:** `src/core/api/v1/foundation/schemas.py`
3. **Functionele beschrijving:** `apply_anonymity_mask(is_anonymous: bool, creator_name: str | None) -> str | None` retourneert `None` als `is_anonymous` waar is, anders de ongewijzigde naam. Op `FoundationContentListItem` en `FoundationContentDetail` een `@model_validator(mode="after")` die `creator_name = apply_anonymity_mask(self.is_anonymous, self.creator_name)` zet. Werkt voor zowel expliciete `model_validate(orm_object)` als impliciete `response_model`-serialisatie.
4. **Randgevallen:** `creator_name=None` + `is_anonymous=False` blijft None (geen crash); lege string blijft ongemoeid; de map-fix uit BE-EP-037 blijft onveranderd werken (die heeft zijn eigen maskering in `content_to_feature`; die mag daar blijven of de helper hergebruiken — kies het schoonste, geen dubbele divergente logica).

### Testplan

**Unit (offline):** mask wel/niet; None-naam; lege string; beide schemas via model_validate met een lichte stub (SimpleNamespace) — geen DB.

**Integratie (Postgres/Redis):**
- list: tenant met 1 anoniem + 1 niet-anoniem APPROVED+PUBLIC item -> anoniem heeft creator_name null, de ander behoudt naam
- detail: anoniem item ophalen -> creator_name null; niet-anoniem -> naam aanwezig
- curatie-queue (met curator-token): anoniem item behoudt creator_name (documenteert O4)
- regressie: bestaande test_content.py blijft groen (fixtures met is_anonymous=True + naam die naam assertten, moeten worden aangepast naar null-verwachting)

## Definition of Done

- [x] Helper + validators gebouwd (`apply_anonymity_mask` + `@model_validator(mode="after")` op ListItem en Detail)
- [x] Unit-tests groen (offline): 9 passed in 0,92s
- [x] Integratietests groen tegen echte Postgres/Redis: 5 passed (list anoniem/niet-anoniem, detail anoniem/niet-anoniem, curatie-queue niet gemaskeerd)
- [x] Bestaande foundation-integratietests groen: regressie test_content.py 23 passed, test_map.py 12 passed, test_curatie.py 18 passed; GEEN lek-vastleggende tests aangetroffen (geen bestaande test seedde is_anonymous=True en assertte daarna een naam)
- [x] Ruff schoon (4 bestanden); mypy 0 issues op schemas.py + map.py; pyright 0 errors op schemas.py + map.py
- [x] Onafhankelijke review (Gate 2) met APPROVED (ronde 1, geen blokkers)
- [x] ID-REGISTRY.md bijgewerkt
- [x] Review-document `docs/backend/review/review-BE-EP-038.md`

---

## Open opvolgpunten

1. **Naam kan alsnog lekken via andere velden (MEDIUM, pre-existing).** `metadata_`, `title_nl`, `title_en`, `body_nl`, `body_en` en `description_*` worden niet gemaskeerd; een uploader die zijn naam in de titel of metadata zet lekt alsnog. Dit is een productbeslissing/UI-communicatiepunt ("plaats geen naam in titel of tekst als je anoniem wilt publiceren"), geen serialisatiebug.
2. **Contract-test aanbevolen (~20 regels).** Een lichte test die vastlegt dat geen publieke response `creator_name` bevat zonder via `apply_anonymity_mask` te gaan. Nu rust de regel op discipline; een toekomstig endpoint dat raw dicts of eigen schemas serialiseert lekt alsnog onopgemerkt.
3. **`is_anonymous` is onflipbaar via de API.** Na aanmaken kan een uploader de vlag niet meer wijzigen of intrekken. Acceptatiecriterium opnemen bij P1-2 (content PUT/DELETE): anonimiteit aanzetten moet altijd kunnen; uitzetten vereist een expliciete bevestiging van de uploader.

---

## Trainingssamenvatting

- **Actor:** Publieke bezoeker of API-consument die publieke content opvraagt via de lijst-, detail- of kaart-endpoints.
- **Voorwaarde:** Erfgoedcontent is aangemaakt met is_anonymous = True ter bescherming van de privacy van de inzender.
- **Actie:** GET /{tenantSlug}/foundation/content, GET /{tenantSlug}/foundation/content/{id} of GET /{tenantSlug}/foundation/map/bbox.
- **Systeemverwerking:** Bij serialisatie van het model naar FoundationContentListItem, FoundationContentDetail of GeoJSON feature properties voert de Pydantic model validator de helper apply_anonymity_mask uit. Als is_anonymous waar is, wordt creator_name vervangen door None. In curatie- en beheer-endpoints blijft de naam zichtbaar voor curatoren.
- **Succesrespons:** HTTP 200 OK met content waarbij creator_name gegarandeerd null is voor anonieme bijdragen in publieke views.
- **Foutrespons:** HTTP 404 indien content niet bestaat of niet publiek/approved is; HTTP 401/403 bij beveiligde beheer-endpoints.
