# Review BE-EP-040: OAI-PMH v2.0 Metadata Harvest Endpoint

STATUS: APPROVED

**Reviewer:** Onafhankelijke review-agent (Gate 2, code-reviewer + quality-reviewer ineen met Red Team mandaat). Code niet zelf geschreven; read-only gereviewd op branch `iter/be-ep-040-oai-pmh`. Verificatie met commando's, unit-, integratietests en architectuuranalyse.  
**Datum:** 2026-09-10  
**Scope:**
- `src/core/services/oai_pmh_service.py` (OaiPmhService, XML serialisatie, resumptionToken signing/decoding, XML sanitization)
- `src/core/api/v1/foundation/oai_pmh.py` (FastAPI router met 6 verbs, HTTP GET/POST handling, keyset cursor query)
- `src/core/shared/public_registry.py` (publieke registratie van `/foundation/oai-pmh`)
- `src/core/api/v1/foundation/router.py` (mounten oai_pmh router)
- `tests/unit/test_foundation_oai_pmh.py` (19 tests)
- `tests/integration/api/v1/foundation/test_oai_pmh.py` (8 tests)
- Spec `docs/backend/features/BE-EP-040-oai-pmh-endpoint.md`, `ID-REGISTRY.md`.  
**Aanleiding:** ADR-029 P0-6 (Cultuursector interoperabiliteit, Europeana / NDE harvesting).

---

## B. Eindoordeel

APPROVED — De implementatie voldoet rigoureus aan de internationale OAI-PMH v2.0 protocolstandaard en de platform-specifieke privacy- en isolatie-eisen. 
Het endpoint retourneert dwingend XML (`text/xml; charset=utf-8`), ondersteunt zowel GET als POST, en implementeert de vereiste foutafhandeling via HTTP status 200 OK met `<error code="...">` tags.
De N-2 invariant (educatieve content en community content komen onder geen beding in de publieke harvest terecht) is zowel op query-niveau als via integratietests met echte PostgreSQL-opslag bewezen. Anonimiteitsmaskering (BE-EP-038) voorkomt dat anonieme makers in Dublin Core `<dc:creator>` lekken. ResumptionTokens zijn beveiligd met HMAC-SHA256 en dwingen parameter-exclusiviteit af.

Alle 19 unit-tests en alle 8 integratietests zijn groen (27/27 PASSED). Ruff check is 100% schoon (0 errors).

---

## C. Samenvatting verificatie

- **Unit tests:** 19/19 PASSED. Dekt XML envelopes, namespace mapping (`oai_dc`, `dc`), XML control character sanitization, parameter validatie voor alle 6 verbs, HMAC tamper-detectie, en anonimiteitsmaskering.
- **Integratie tests:** 8/8 PASSED (tegen echte PostgreSQL :5435). Verifieert HTTP GET en POST voor `Identify`, `ListMetadataFormats`, `ListSets`, `ListRecords`, N-2 uitsluiting van `EDU` en `PENDING` content, maskering van anonieme auteurs, uitstoot van `<header status="deleted">` bij `ContentStatus.REMOVED`, en protocolfouten (`badVerb`, `badArgument`, `idDoesNotExist`).
- **Code kwaliteit:** Ruff check schoon. Geen non-ASCII karakters in broncode of comments. Geen verboden `datetime.now()` of `datetime.utcnow()` (alles netjes via `utc_now()` en `to_utc()` helpers).

---

## D. Bevindingen per categorie

1. **Protocolconformiteit OAI-PMH v2.0:**
   Alle 6 verbs (`Identify`, `ListMetadataFormats`, `ListSets`, `GetRecord`, `ListIdentifiers`, `ListRecords`) zijn geïmplementeerd en conform de specificatie. Foutmeldingen gebruiken de verplichte foutcodes (`badVerb`, `badArgument`, `cannotDisseminateFormat`, `idDoesNotExist`, `noRecordsMatch`, `badResumptionToken`) en worden geretourneerd onder HTTP 200 OK.
2. **N-2 Invariant & Privacy:**
   In `src/core/api/v1/foundation/oai_pmh.py` filtert de databasequery strikt op:
   `FoundationContent.tenant_id == tenant.id`, `FoundationContent.visibility == Visibility.PUBLIC`, en `FoundationContent.status.in_([ContentStatus.APPROVED, ContentStatus.REMOVED])`.
   Hierdoor is wiskundig uitgesloten dat educatieve content (`visibility == EDU`, Sprint D) of ongekeurde concepten ooit via OAI-PMH worden gelekt.
3. **Anonimiteitsmaskering (BE-EP-038):**
   In `_build_dublin_core` wordt `record.creator` alleen toegevoegd aan `<dc:creator>` indien `not record.is_anonymous`. Dit voorkomt schending van AVG/GDPR bij anoniem ingezonden verhalen en audio-opnames.
4. **Flow Control & Exclusiviteit (ResumptionToken):**
   De specificatie eist dat een aanvraag met `resumptionToken` geen andere argumenten bevat behalve `verb`. Dit wordt strikt gevalideerd in `_validate_arguments`; bij schending volgt direct `badArgument`. Tokens zijn beveiligd met HMAC-SHA256 inclusief tenant slug en verloopdatum (24 uur), waardoor token manipulation onmogelijk is.
5. **Deleted Records Transient:**
   `Identify` adverteert `deletedRecord="transient"`. Verwijderde items (`ContentStatus.REMOVED`) worden conform OAI-PMH uitgeleverd als `<header status="deleted">` zonder `<metadata>` body. Harvesters kunnen hiermee hun index actualiseren.
6. **XML Injection & Control Characters:**
   `OaiPmhService._sanitize_xml_str` verwijdert illegale XML 1.0 control characters (0x00-0x08, 0x0B-0x0C, 0x0E-0x1F) die parser-crashes kunnen veroorzaken bij aggregators.

---

## E. Issue register

| Severity | Locatie | Probleem | Correctie / Aanbeveling |
|---|---|---|---|
| MEDIUM | `src/core/api/v1/foundation/oai_pmh.py` (Paginatie) | Paginatie gebruikt op dit moment SQL `OFFSET`/`LIMIT` binnen het gesignde resumptionToken. Bij enorme collecties (>100.000 records) wordt diepe scanning traag. | Voor Fase 2 optimaliseren naar zuivere keyset-paginatie (`WHERE id > :cursor_id ORDER BY id ASC LIMIT :batch_size`). |
| LOW | `src/core/api/v1/foundation/oai_pmh.py` (Rate Limiting) | Endpoint heeft nog geen specifieke OAI-PMH rate limiter met `HTTP 503 Retry-After` header conform RFC 6585 / OAI-PMH best practice. | Voor aggregators zoals Europeana is een `503 Service Unavailable` met `Retry-After: 60` protocolconform en voorkomt server-overbelasting tijdens bulk harvests. |
| LOW | `src/core/services/oai_pmh_service.py` | Sets zijn momenteel 1-op-1 gemapt op `ContentType` waarden. Geen ondersteuning voor hiërarchische sets (`collection:oorlog`, `thema:slavernij`). | In een latere sprint sets optioneel koppelen aan taxonomie-tags of collecties. |

---

## F. Release-oordelen

- Bouw/implementatie: **JA (GO)**
- QA/geautomatiseerd testen: **JA (GO)** (27/27 tests geslaagd, incl. protocol validaties)
- Architectuur & Security: **JA (GO)** (N-2 invariant waterdicht, anonimiteit conform BE-EP-038)
- Red Team Review: **APPROVED**

---

## Wat wél klopt

- **Strikte OAI-PMH protocolconformiteit:** De beslissing om HTTP 200 terug te geven bij protocolfouten met een `<error>` tag is contra-intuïtief voor moderne REST API ontwikkelaars, maar 100% verplicht voor erfgoedharvesters. Dat dit correct is geïmplementeerd voorkomt directe afkeuring door NDE / Europeana validators.
- **HMAC-stateless tokens:** Geen geheugenbelasting of zwevende sleutels in Redis voor resumptionTokens. Tokens zijn stateless, cryptografisch beschermd en hebben een automatische vervaltermijn van 24 uur.
- **Defensieve XML parsing:** Zowel `ElementTree` escaping als actieve Unicode control character filtering voorkomen corrupte feeds.
- **N-2 invariant handhaving:** Zowel in SQL-query als in serializers is geborgd dat niet-publieke data categorisch is uitgesloten.

---

## Devil's Advocate — Waarom faalt deze oplossing in de toekomst?

1. **De `OFFSET`-valkuil bij miljoenen records:**
   De huidige resumptionToken implementatie encodeert een integer `offset`. In PostgreSQL betekent `OFFSET 100000` dat de database-engine 100.000 rijen moet ophalen, controleren en weggooien voordat de volgende 100 rijen worden teruggestuurd. Zodra een stichting een archief van honderdduizenden gedigitaliseerde foto's of documenten ontsluit en Delpher of Europeana een volledige her-indexatie start, zal de database I/O exponentieel toenemen en de query response time degraderen tot timeouts.
2. **De HTTP 429 vs HTTP 503 Harvester Breuk:**
   Als een generieke FastApi rate-limiter op dit endpoint wordt gezet, retourneert FastAPI standaard `HTTP 429 Too Many Requests` met een JSON error body (`{"detail": "Rate limit exceeded"}`). Voor een OAI-PMH crawler is een JSON 429 een fatale protocolcrash waardoor de harvest onmiddellijk faalt en het archief als 'onbereikbaar' wordt gemarkeerd. Harvesters verwachten volgens de OAI-PMH specificatie `HTTP 503 Service Unavailable` met een `Retry-After: <seconden>` header.
3. **Horizontale schaalbaarheid en Secret Key rotatie:**
   Omdat de resumptionToken wordt ondertekend met de applicatie `SECRET_KEY`, zal elke rotatie van dit geheim lopende harvests van externe instellingen (die vaak dagen duren voor grote collecties) direct afbreken met een `badResumptionToken` fout.
