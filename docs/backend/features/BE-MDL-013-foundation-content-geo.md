# Backend Feature Specification -- BE-MDL-013

## Metadata

- Feature ID: BE-MDL-013
- Feature naam: FoundationContent Geo + Metadata Velduitbreiding
- Status: IMPLEMENTED
- Auteur: Backend Documentatie Agent
- Reviewer: (te reviewen)
- Datum: 2026-08-24
- Gerelateerde user story / ticket: ADR-029 Foundation Portal -- Dag 1
- Gerelateerde router / module: `src/core/models/foundation_content.py`
- Gerelateerde frontend endpoints: (frontend spec volgt in aparte sprint)
- Gerelateerde database tabellen: `foundation_content`
- Versie: 1.0

---

## Doel en scope

### Doel

Uitbreiden van het `FoundationContent` model met geo-locatievelden (lat/lng, location_name),
licentie-informatie, categorisatie en een flexibel JSONB metadata-veld. Dit maakt
geo-gefilterde content-opslag, licentie-naleving en rich metadata mogelijk voor het
Foundation Portal (ADR-029).

### In scope

- `FoundationContent`: 6 nieuwe velden (+lat, +lng, +location_name, +license, +category, +metadata JSONB)
- PostgreSQL GIST expression-index op `point(lng, lat)` voor geo-queries zonder PostGIS
- PostgreSQL GIN-index op `metadata` JSONB voor snelle JSONB-lookups
- Alembic migratie `20260824_adr029_portal_v1` (sectie 2)
- Model-defaults en schema-validatie

### Out of scope

- PostGIS-extensie (expression-index met `point()` is voldoende voor MVP)
- Frontend kaart-componenten (ADR-029 frontend sprint)
- API-endpoints voor geo-zoeken (volgt in latere sprint)
- Content-tagging AI-pipeline

---

## Build summary

- Nieuw gebouwd:
  - `lat`, `lng`, `location_name`, `license`, `category`, `metadata_` velden op `FoundationContent`
  - `idx_fc_geo` GIST index (`point(lng, lat)`) conditioneel op non-NULL
  - `idx_fc_metadata` GIN index op JSONB
- Gewijzigd:
  - `src/core/models/foundation_content.py` -- 6 velden toegevoegd
  - `src/alembic/versions/20260824_adr029_portal_v1.py` -- migratie + indexen
- Verwijderd: --
- Beinvloede bestaande flows:
  - `FoundationContent` instantiatie in bestaande tests (backward-compatibel: alle velden zijn nullable)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-MDL-013 | FoundationContent geo + metadata | Model | `src/core/models/foundation_content.py` | Wijziging | Content upload, geo-filter, audit export |
| BE-MIG-029-001 | adr029_portal_v1 (sectie 2) | Migratie | `src/alembic/versions/20260824_adr029_portal_v1.py` | Nieuw | -- |

---

## Detaildocumentatie per artefact

---

## [BE-MDL-013] FoundationContent -- Geo + Metadata velden

### 1. Type

SQLAlchemy 2.0 ORM Model (asyncpg-compatibel) -- velduitbreiding op bestaand model

### 2. Locatie

- Bestandspad: `src/core/models/foundation_content.py`
- Klasse: `FoundationContent`
- Base: `src.core.database.database.Base`

### 3. Gerelateerde flow

- Content upload flow (frontend -> API -> DB)
- Geo-gefilterde content-opvraging (toekomstige endpoint)
- GDPR DSAR export (metadata bevat mogelijk PII)

### 4. Doel

Content-items kunnen geo-gelokaliseerd, gelicenseerd, gecategoriseerd en verrijkt
met vrije JSON-metadata worden opgeslagen, zonder schema-migraties bij elke
nieuwe metadata-behoefte.

### 5. Functionele beschrijving

Elk content-item kan optioneel een geografische locatie hebben (latitude en
longitude als float, plus een leesbare location_name-string). Een license-veld
slaat de Creative Commons of andere licentie op. Het category-veld geeft een
vrije categorie-string (bijv. "heritage", "oral_history"). Het metadata-veld
is een JSONB-object dat vrije structuur toestaat (bijv. `{"year": 2024,
"source": "archive"}`).

### 6. Technische beschrijving

```python
class FoundationContent(Base):
    # ... bestaande velden ...

    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    license: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=dict
    )
```

Indexen:
- `idx_fc_geo` -- GIST expression-index: `point(lng, lat)` WHERE lat IS NOT NULL AND lng IS NOT NULL
- `idx_fc_metadata` -- GIN index op `metadata` JSONB

Bestaande indexen (onveranderd):
- `idx_fc_tenant_status` -- (tenant_id, status)
- `idx_fc_tenant_type_status` -- (tenant_id, type, status)
- `idx_fc_tenant_created` -- (tenant_id, created_at)

Migratie-upgrade voegt de kolommen toe met `server_default="'{}'::jsonb"` voor
`metadata`. De downgrade verwijdert de kolommen in omgekeerde volgorde en
verwijdert de twee conditionele indexen.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT (endpoint-laag; model zelf heeft geen auth)
- Vereiste rol / scope: endpoint-afhankelijk
- Tenant-isolatie: `tenant_id` NOT NULL + FK CASCADE + ORM `do_orm_execute` hook (ADR-004) + RLS policy (ADR-005)
- Feature flag: --

### 8. Request-specificatie

NVT -- dit is een model, geen endpoint.

### 9. Response-specificatie

NVT -- dit is een model, geen endpoint.

### 10. Validaties en constraints

- `lat`, `lng`: `Float`, nullable. Geen database-check op geldig bereik (-90/90, -180/180); applicatie-validatie advised.
- `location_name`: `String(200)`, nullable.
- `license`: `String(50)`, nullable. Vrij formaat; validatie in endpoint-laag advised.
- `category`: `String(100)`, nullable.
- `metadata`: `JSONB`, nullable, server_default=`'{}'::jsonb`. Python-side default=`dict`.
- Alle velden zijn backward-compatibel (nullable of met default).

### 11. Business rules

- Geo-velden zijn optioneel. Als `lat` of `lng` NULL is, wordt het item niet in
de geo-index opgenomen.
- `metadata` JSONB wordt nooit geschematiseerd op database-niveau; structuur
definieert de applicatielaag.
- Licentie-informatie is puur informatief op model-niveau; enforcement gebeurt
in de upload- en publicatie-flow.

### 12. Afhankelijkheden

- `src.core.database.database.Base`
- PostgreSQL 15+ (JSONB, GIST, GIN, expression-indexen)
- `tenants` tabel bestaat (FK)
- Alembic-migratie `20260824_adr029_portal_v1`

### 13. Foutafhandeling

- 500: `IntegrityError` bij ongeldige tenant_id (FK violation)
- 500: Database-fout bij ontbrekende migratie
- 500: `DataError` bij te lange `location_name` (>200), `license` (>50), of `category` (>100)
- 400 (endpoint-laag): Ongeldige `lat`/`lng` buiten geografisch bereik

### 14. Transacties en data-integriteit

- `metadata` server_default `'{}'::jsonb` zorgt dat bestaande rijen na migratie
een leeg JSONB-object krijgen in plaats van NULL.
- GIST-index is conditioneel (`WHERE lat IS NOT NULL AND lng IS NOT NULL`);
dit voorkomt index-bloat voor rijen zonder geo-data.
- Downgrade dropt eerst de indexen, dan pas de kolommen, om constraint-fouten
te voorkomen.

### 15. Telemetry / logging / tracing

NVT op model-niveau. Endpoints loggen `tenant_id` + `content_id` bij mutaties.

### 16. Caching

NVT.

### 17. Acceptatiecriteria

- [x] `lat` en `lng` zijn `Float`, nullable, zonder check-constraint
- [x] `location_name` is `String(200)`, nullable
- [x] `license` is `String(50)`, nullable
- [x] `category` is `String(100)`, nullable
- [x] `metadata` is `JSONB`, nullable, met server_default `'{}'::jsonb`
- [x] GIST-index `idx_fc_geo` bestaat conditioneel op non-NULL lat/lng
- [x] GIN-index `idx_fc_metadata` bestaat op `metadata`
- [x] Migratie-upgrade voegt velden toe zonder data-verlies
- [x] Migratie-downgrade verwijdert velden + indexen in correcte volgorde
- [x] Bestaande `FoundationContent` instantiatie zonder nieuwe velden werkt
- [x] `FoundationContent` met geo/metadata kan succesvol worden aangemaakt (test: `test_foundation_content_with_geo`)
- [x] `metadata` accepteert willekeurig JSON-object

### 18. Integratoruitleg

- Importeer `FoundationContent` van `src.core.models.foundation_content`.
- Alle 6 nieuwe velden zijn optioneel; bestaande code blijft werken zonder wijzigingen.
- `metadata` is een Python `dict` dat direct aan het model-veld kan worden toegewezen.
- Voor geo-queries: gebruik `ST_DWithin` of vergelijk `point(lng, lat)` met de
GIST-index (PostgreSQL-specifiek).

### 19. Trainingssamenvatting

| Veld | Inhoud |
|------|--------|
| Actor | Backend systeem / Content upload endpoint |
| Voorwaarde | PostgreSQL bereikbaar, Alembic migratie `20260824_adr029_portal_v1` uitgevoerd |
| Actie | Maak of wijzig `FoundationContent` met optionele geo/metadata velden |
| Systeemverwerking | SQLAlchemy INSERT/UPDATE; GIST/GIN-indexen bijgewerkt door PostgreSQL |
| Succesrespons | Content-object met ingevulde geo/metadata velden |
| Foutrespons | IntegrityError bij FK-fout; DataError bij te lange strings |
| Uitzonderingen | Migratie niet uitgevoerd: kolommen ontbreken -> 500 bij INSERT |

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- Het `FoundationContent` model ondersteunt vanaf deze versie geografische
coordinaten, licentie-informatie, categorisatie en vrije JSON-metadata.
- Alle uitbreidingen zijn optioneel; er is geen breaking change voor bestaande
consumers.
- Geo-data wordt opgeslagen als losse `lat`/`lng` floats plus een leesbare
`location_name`. De database gebruikt een GIST-index voor efficiente geo-queries.
- `metadata` is een vrije JSONB-blob. De structuur wordt niet afgedwongen op
database-niveau; documenteer afspraken in het team.

---

## Open aannames

- `lat`/`lng` validatie op bereik (-90/90, -180/180) gebeurt in de endpoint-/servicelaag,
niet in het ORM-model.
- `license` en `category` gebruiken vrije tekst; er is geen enum of controlled
vocabulary op model-niveau.
- `metadata` JSONB-structuur is niet geschematiseerd; Pydantic-validatie in de
API-laag wordt aanbevolen.

## Open vragen

- Moet `metadata` een Pydantic-schema krijgen in de API-laag voor structuur-validatie?
- Moeten `license` en `category` enums worden in een latere iteratie?

## Risico's

- GIST expression-index `point(lng, lat)` werkt alleen op PostgreSQL. SQLite
tests die de index proberen aan te maken falen; migratie bevat `_is_postgresql()`
guard.
- JSONB `metadata` kan ongeldige structuren bevatten als de API-laag niet
valideert. Aanbeveling: Pydantic-schema in request DTO.

---

## QA-checks

- [x] Model constraints getest (nullable, defaults, JSONB-type)
- [x] Tenant-isolatie op model-niveau bevestigd (RLS + NOT NULL tenant_id)
- [x] Alembic migratie getest (upgrade + downgrade)
- [x] Indexen geverifieerd (GIST conditioneel, GIN op JSONB)
- [x] Backward-compatibiliteit: oude instantiatie zonder nieuwe velden werkt
- [x] Geo-metadata instantiatie getest (`test_foundation_content_with_geo`)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle modellen zijn geinventariseerd
- [x] Acceptatiecriteria zijn testbaar
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [ ] Review door reviewer-prompt: (nog uit te voeren)
