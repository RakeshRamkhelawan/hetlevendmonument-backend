# Backend Feature Specification

## Metadata

| Veld | Waarde |
|------|--------|
| Feature ID | BE-EP-040 |
| Naam | OAI-PMH v2.0 Metadata Harvest Endpoint (`/{tenantSlug}/foundation/oai-pmh`) |
| Status | Klaar / Geïmplementeerd |
| Auteur | AI-agent (senior architect-rol) |
| Reviewer | PENDING (Gate 2 Review) |
| Datum | 2026-09-10 |
| User story / ticket | ADR-029 `docs/adr/029-foundation-portal-architecture.md` regels 203-210 (cultuursector interoperabiliteit); Audit gap P0-6; Sprint brief `docs/agent-briefs/generated/2026-09-10-sprint-dag-adr029-p0-6-oai-pmh.md` |
| Router / module | `src/core/api/v1/foundation/oai_pmh.py` (nieuw), `src/core/services/oai_pmh_service.py` (nieuw), `src/core/shared/public_registry.py` (gewijzigd), `src/core/api/v1/foundation/router.py` (gewijzigd) |
| Frontend / Consumer endpoints | `GET /{tenantSlug}/foundation/oai-pmh`, `POST /{tenantSlug}/foundation/oai-pmh` |
| Database tabellen | `foundation_content` (lezen, filter visibility=public, status in (APPROVED, REMOVED)); geen migratie |
| Versie | 1.0 |

## Doel en scope

### Doel

Implementatie van een volledig OAI-PMH v2.0 (Open Archives Initiative Protocol for Metadata Harvesting) compliant endpoint ten behoeve van erfgoedinstellingen, aggregators (zoals Europeana, Netwerk Digitaal Erfgoed / NDE, Delpher) en academische harvesters. Het endpoint ontsluit publieke collectie-metadata in Dublin Core (`oai_dc`) formaat met strikte handhaving van multi-tenancy, platform-integriteitsregels en privacy-invarianten.

### In scope

- **Protocolconformiteit OAI-PMH v2.0**:
  - Volledig XML response format met `Content-Type: text/xml; charset=utf-8` (nooit JSON, zelfs niet bij fouten).
  - Volledige ondersteuning van zowel **HTTP GET** als **HTTP POST** (`application/x-www-form-urlencoded`).
  - Foutafhandeling conform sectie 3.1.2: Protocol- en validatiefouten retourneren verplicht **HTTP status 200 OK** met een `<error code="...">` XML-element. Foutcodes: `badVerb`, `badArgument`, `cannotDisseminateFormat`, `idDoesNotExist`, `noRecordsMatch`, `badResumptionToken`.
  - Ondersteuning van alle 6 OAI-PMH protocol verbs:
    1. `Identify`: Geeft repository-identiteit, admin-email, protocolversie 2.0, vroegste datestamp en deletedRecord-beleid (`transient`).
    2. `ListMetadataFormats`: Adverteert ondersteunde schema's (inclusief `oai_dc`, schema URL `http://www.openarchives.org/OAI/2.0/oai_dc.xsd`).
    3. `ListSets`: Mapt content-types naar sets (bijv. `story`, `audio`, `artwork`, etc.).
    4. `GetRecord`: Haalt één specifiek record op op basis van unieke identifier (`oai:{tenantSlug}:{id}`).
    5. `ListIdentifiers`: Selectieve harvest van headers (met optionele `from`, `until`, `set`, `metadataPrefix`).
    6. `ListRecords`: Volledige metadata harvest inclusief Dublin Core `<metadata>` records.
- **Inhoudelijke Integriteitsregels & Invarianten**:
  - **N-2 Invariant (Absolute uitsluiting niet-publieke content)**: Uitsluitend items met `visibility == Visibility.PUBLIC` worden geoogst. Educatieve content (`visibility == EDU`, Sprint D) en community content (`visibility == COMMUNITY`) verschijnen onder GEEN BEDING in de harvester feed.
  - **Statusfiltering**: Alleen `ContentStatus.APPROVED` items worden met volledige metadata uitgeleverd.
  - **Deleted Record Transient Support**: Verwijderde items (`ContentStatus.REMOVED`) worden conform OAI-PMH specificatie opgenomen in de harvest met `<header status="deleted">` zonder `<metadata>` block, zodat harvesters hun lokale index kunnen opschonen.
  - **Anonimiteitsmaskering (BE-EP-038)**: Wanneer `is_anonymous == True`, wordt de `creator_name` strikt weggelaten uit het Dublin Core `<dc:creator>` veld.
  - **Dublin Core Mapping**: Mapping van `FoundationContent` naar Dublin Core velden: `dc:title`, `dc:creator`, `dc:description`, `dc:date`, `dc:type`, `dc:rights`, `dc:coverage` (location), `dc:identifier`.
  - **Flow Control (ResumptionToken)**:
    - Veilige, stateless keyset-paginatie met HMAC-SHA256 handtekening en vervaldatum (TTL = 24 uur).
    - Detectie van argumentexclusiviteit: een request met `resumptionToken` mag GEEN andere parameters bevatten behalve `verb` (overtreding resulteert direct in `badArgument`).
    - XML-sanitization van alle gebruikersinvoer ter voorkoming van XML injection of illegale XML 1.0 control characters (ASCII < 32 met uitzondering van tab, LF, CR).
- **Infrastructuur & Routing**:
  - Publieke router registratie in `src/core/shared/public_registry.py`: `/foundation/oai-pmh` toegevoegd zodat harvesters zonder Bearer token toegang hebben.
  - Multi-tenant isolatie via URL-pad: `/{tenantSlug}/foundation/oai-pmh`.

### Out of scope

- Complexe MARC21, EDM (Europeana Data Model) of MODS metadata prefixen (MVP is strikt Dublin Core `oai_dc`).
- Dynamische OAI-PMH sets gebaseerd op taxonomietags (MVP setSpecs zijn gebaseerd op `ContentType`).
- Stateful sessie-opslag in Redis voor resumption tokens (stateless HMAC-signed token is lichter en veerkrachtiger).

## Ontwerpbeslissingen

| # | Beslissing | Reden |
|---|-----------|-------|
| O1 | XML serialisatie via Python `xml.etree.ElementTree` met expliciete namespace maps | Lichtgewicht, ingebouwd in Python standaard library, geen externe afhankelijkheid van zware XML frameworks zoals `lxml`. Veilige escaping van attributen en tekst nodes. |
| O2 | Protocolfouten als HTTP 200 XML `<error>` | OAI-PMH v2.0 specificatie vereist dwingend HTTP 200 met XML body bij applicatiefouten. HTTP 4xx/5xx breekt externe harvesters zoals OAIster en NDE aggregators. |
| O3 | Keyset resumptionToken met HMAC-SHA256 signing | Stateless en schaalbaar; voorkomt token-spoofing en SQL-injectie in paginatie-parameters; overleeft server-restarts en vereist geen Redis load. |
| O4 | Uniforme sanitization van Unicode / XML control characters | XML 1.0 verbiedt control characters (0x00-0x08, 0x0B-0x0C, 0x0E-0x1F). Deze worden gestript om parser-crashes bij harvesters te voorkomen. |
| O5 | Strikte argument-validatie per verb | OAI-PMH specificatie eist dat onbekende of inconsistente argumenten onmiddellijk worden afgewezen met `badArgument`. |
| O6 | Dublin Core anonimiteit conform BE-EP-038 | Voorkomt privacylekken van anonieme getuigenissen in openbare culturele harvests. |

## Build summary

### Nieuw gebouwd

- `src/core/services/oai_pmh_service.py`:
  - `OaiPmhService`: XML builder, namespace mapping, Dublin Core generator, resumptionToken builder & decoder (HMAC-SHA256), XML sanitizer.
  - Data structuren: `OaiRecord`, `OaiHeader`, `OaiIdentifyInfo`, `OaiMetadataFormat`, `OaiSet`.
- `src/core/api/v1/foundation/oai_pmh.py`:
  - FastAPI router die zowel GET als POST accepteert.
  - Dispatcher voor alle 6 OAI-PMH verbs.
  - Keyset database query paging met status- en visibility filtering.
- Tests:
  - `tests/unit/test_foundation_oai_pmh.py`: 19 offline tests voor protocol parsing, serialisatie, XML escaping, token signing en exclusiviteit.
  - `tests/integration/api/v1/foundation/test_oai_pmh.py`: 8 end-to-end tests tegen echte PostgreSQL test database.

### Gewijzigd

- `src/core/shared/public_registry.py`: Registratie van `/foundation/oai-pmh` als publiek endpoint.
- `src/core/api/v1/foundation/router.py`: Mounten van de `oai_pmh.router`.
- `docs/backend/features/ID-REGISTRY.md`: Toevoegen van `BE-EP-040`.

## Testplan

### Unit Tests (`tests/unit/test_foundation_oai_pmh.py`)
- XML namespaces conform OAI-PMH v2.0 en OAI-DC.
- XML sanitizer verwijdert illegale karakters.
- Identify XML formatting met protocolVersion 2.0 en deletedRecord=transient.
- ListMetadataFormats en ListSets XML generatie.
- ResumptionToken encoding/decoding en tamper-detectie (HMAC failure).
- Error XML generatie voor badVerb, badArgument, cannotDisseminateFormat, idDoesNotExist, noRecordsMatch, badResumptionToken.

### Integratietests (`tests/integration/api/v1/foundation/test_oai_pmh.py`)
- Echte HTTP requests via AsyncClient tegen PostgreSQL.
- Verificatie van GET en POST methodes.
- N-2 invariant: Edu- en pending records ontbreken gegarandeerd in ListRecords.
- Anonieme content: `is_anonymous=True` maskeert maker in `<dc:creator>`.
- Verwijderde content: `status=REMOVED` verschijnt als `<header status="deleted">` zonder `<metadata>`.
- ResumptionToken exclusiviteit: combinatie met metadataPrefix faalt met HTTP 200 `badArgument`.
- Onbekende ID geeft HTTP 200 `idDoesNotExist`.

---

## Trainingssamenvatting

- **Actor:** Externe erfgoedaggregator of harvester (zoals Netwerk Digitaal Erfgoed / Europeana) die metadata oogst.
- **Voorwaarde:** Een geldige OAI-PMH HTTP GET of POST request met een ondersteund werkwoord (verb: Identify, ListMetadataFormats, ListSets, GetRecord, ListIdentifiers, ListRecords).
- **Actie:** GET /{tenantSlug}/foundation/oai-pmh?verb=ListRecords&metadataPrefix=oai_dc.
- **Systeemverwerking:** De endpoint valideert de protocolparameters, sanitizeert input tegen XML control characters, controleert exclusiviteit van resumptionToken, haalt publieke goedgekeurde records op met uitsluiting van educatieve content (N-2 invariant), maskeert anonieme makers conform BE-EP-038 in Dublin Core <dc:creator>, en genereert een XML-document conform OAI-PMH 2.0 specificatie met eventuele HMAC-ondertekende resumption tokens.
- **Succesrespons:** HTTP 200 OK met XML media-type text/xml bevattende het geldige OAI-PMH XML antwoord.
- **Foutrespons:** HTTP 200 OK met OAI-PMH error blok conform protocol bij ongeldige argumenten, niet-ondersteunde metadataPrefix of niet-bestaande identifiers; HTTP 404 alleen indien de tenant slug onbekend is.
