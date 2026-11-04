# Backend Feature Specification -- BE-MDL-015

## Metadata

- Feature ID: BE-MDL-015
- Feature naam: EducationalAccess + StudyCollection Modellen
- Status: IMPLEMENTED
- Auteur: Backend Documentatie Agent
- Reviewer: (te reviewen)
- Datum: 2026-08-24
- Gerelateerde user story / ticket: ADR-029 Foundation Portal -- Dag 1
- Gerelateerde router / module: `src/core/models/foundation_content.py`
- Gerelateerde frontend endpoints: (frontend spec volgt in aparte sprint)
- Gerelateerde database tabellen: `educational_access`, `study_collections`
- Versie: 1.0

---

## Doel en scope

### Doel

Introduceren van twee nieuwe modellen voor educatieve toegangsbeheering binnen
het Foundation Portal:
1. `EducationalAccess` -- toegangscodes die leraren en leerlingen toegang geven
to study collections binnen een tenant.
2. `StudyCollection` -- een verzameling lesmaterialen gekoppeld aan een
toegangscode.

Dit maakt het mogelijk om gecureerde educatieve content beschikbaar te stellen
aan scholen en klaslokalen met fijnmazige toegangscontrole.

### In scope

- `EducationalAccess` model (RLS, tenant_id NOT NULL, unieke code, rol-enum)
- `StudyCollection` model (RLS, tenant_id NOT NULL, access_code index)
- `EducationalRole` enum (TEACHER, STUDENT, ADMIN, CURATOR, VISITOR)
- Alembic migratie `20260824_adr029_portal_v1` (secties 4 + 5)
- Unieke constraints op tenant+code (EducationalAccess) en tenant+access_code
  index (StudyCollection)

### Out of scope

- API-endpoints voor toegangscodes genereren/verifieren (toekomstige sprint)
- Koppeling tussen StudyCollection en FoundationContent (many-to-many tabel
  volgt in latere iteratie)
- Frontend educatieve dashboard (ADR-029 frontend sprint)
- Automatische e-mailuitnodigingen bij code-generatie

---

## Build summary

- Nieuw gebouwd:
  - `EducationalAccess` ORM model + `educational_access` tabel
  - `StudyCollection` ORM model + `study_collections` tabel
  - `EducationalRole` enum (5 waarden)
  - `educational_role_enum` PostgreSQL ENUM
  - RLS policies voor beide tabellen (safe NULLIF pattern, ADR-005)
- Gewijzigd:
  - `src/core/models/foundation_content.py` -- 2 nieuwe modellen + 1 enum
  - `src/alembic/versions/20260824_adr029_portal_v1.py` -- create_table + RLS
- Verwijderd: --
- Beinvloede bestaande flows: -- (geen breaking changes)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-MDL-015-A | EducationalAccess | Model | `src/core/models/foundation_content.py` | Nieuw | Edu toegangsverificatie, code-generatie |
| BE-MDL-015-B | StudyCollection | Model | `src/core/models/foundation_content.py` | Nieuw | Lesmateriaal weergave, educatieve zoekflow |
| BE-MIG-029-001 | adr029_portal_v1 (secties 4+5) | Migratie | `src/alembic/versions/20260824_adr029_portal_v1.py` | Nieuw | -- |

---

## Detaildocumentatie per artefact

---

## [BE-MDL-015-A] EducationalAccess

### 1. Type

SQLAlchemy 2.0 ORM Model (asyncpg-compatibel) -- nieuw model

### 2. Locatie

- Bestandspad: `src/core/models/foundation_content.py`
- Klasse: `EducationalAccess`
- Enum: `EducationalRole`
- Base: `src.core.database.database.Base`

### 3. Gerelateerde flow

- Educatieve toegangscode verificatie-flow (toekomstig endpoint)
- PortalUser rol-escalatie (VISITOR -> STUDENT/TEACHER via code)
- GDPR DSAR export (educatieve deelnemers hebben PII)

### 4. Doel

Een herbruikbare toegangscode verlenen aan een e-mailadres binnen een tenant,
met een specifieke educatieve rol. De code kan verlopen (`expires_at`) of
deactiveren (`is_active`).

### 5. Functionele beschrijving

Een docent of beheerder genereert een toegangscode (bijv. "EDU2024A").
Leerlingen en leraren gebruiken deze code om toegang te krijgen tot een
`StudyCollection`. Elke code is uniek per tenant en gekoppeld aan een e-mailadres.
De `role` bepaalt of de gebruiker als leraar of leerling wordt aangemerkt.

### 6. Technische beschrijving

```python
class EducationalRole(str, enum.Enum):
    TEACHER = "teacher"
    STUDENT = "student"
    ADMIN = "admin"
    CURATOR = "curator"
    VISITOR = "visitor"

class EducationalAccess(Base):
    __tablename__ = "educational_access"
    __table_args__ = (
        Index("idx_ea_tenant_code", "tenant_id", "code", unique=True),
        Index("idx_ea_tenant_email", "tenant_id", "email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[EducationalRole] = mapped_column(
        PGEnum(EducationalRole, name="educational_role_enum"),
        default=EducationalRole.STUDENT, nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
```

RLS policy (migratie):
```sql
ALTER TABLE educational_access ENABLE ROW LEVEL SECURITY;
CREATE POLICY educational_access_tenant_isolation
  ON educational_access FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::int);
```

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT of magic-link sessie (endpoint-laag)
- Vereiste rol / scope: endpoint-afhankelijk; code-verificatie endpoint is
  typisch publiek (binnen tenant-context)
- Tenant-isolatie: RLS + NOT NULL tenant_id + ORM hook (ADR-004)
- Feature flag: --

### 8. Request-specificatie

NVT -- dit is een model, geen endpoint.

### 9. Response-specificatie

NVT -- dit is een model, geen endpoint.

### 10. Validaties en constraints

- `tenant_id`: NOT NULL, FK(tenants.id, CASCADE), index
- `code`: `String(20)`, NOT NULL, uniek op database-niveau (globaal uniek)
  *Aantekening*: composite unique index `idx_ea_tenant_code` maakt code uniek
  per tenant; `unique=True` op kolom-niveau maakt het globaal uniek. Dit is
  een bewuste keuze om code-conflicten over tenants heen te voorkomen.
- `email`: `String(255)`, NOT NULL, index
- `role`: `educational_role_enum`, NOT NULL, default=STUDENT
- `is_active`: `Boolean`, NOT NULL, default=True
- `expires_at`: `DateTime(tz)`, nullable

### 11. Business rules

- Een code kan maar door een gebruiker worden gebruikt (1:1 met e-mailadres,
  hoewel het model dit niet strikt afdwingt op database-niveau).
- `is_active=False` deactiveert de code onmiddellijk, ongeacht `expires_at`.
- Bij verlopen (`expires_at < now()`) moet de applicatie de code afwijzen,
  ongeacht `is_active`.
- Code-verificatie moet altijd binnen de juiste tenant-context gebeuren.

### 12. Afhankelijkheden

- `src.core.database.database.Base`
- PostgreSQL 15+ (ENUM, RLS)
- `tenants` tabel bestaat (FK)
- Alembic-migratie `20260824_adr029_portal_v1`

### 13. Foutafhandeling

- 500: `IntegrityError` bij dubbele `code` (unieke constraint)
- 500: Database-fout bij ontbrekende migratie
- 400 (endpoint-laag): Ongeldige `EducationalRole`-waarde
- 409 (endpoint-laag): Code bestaat al binnen tenant
- 403 (endpoint-laag): Code is inactive of verlopen

### 14. Transacties en data-integriteit

- `code` is globaal uniek via `unique=True` op kolom-niveau.
- Tenant-scoped uniekheid via composite index `idx_ea_tenant_code`.
- Downgrade dropt tabel na policy+RLS disable; orphaned `educational_role_enum`
  wordt expliciet opgeruimd in downgrade.

### 15. Telemetry / logging / tracing

NVT op model-niveau.

### 16. Caching

NVT.

### 17. Acceptatiecriteria

- [x] `EducationalAccess` is importeerbaar vanuit `src.core.models.foundation_content`
- [x] `tenant_id` is NOT NULL
- [x] `code` is NOT NULL, globaal uniek (unique=True)
- [x] `email` is NOT NULL, geindexeerd
- [x] `role` default=STUDENT, NOT NULL
- [x] `is_active` default=True, NOT NULL
- [x] `expires_at` is nullable
- [x] RLS policy aanwezig in migratie
- [x] Succesvolle creatie getest (`test_educational_access_create`)
- [x] Duplicatie-integrity getest (`test_educational_access_duplicate_code_raises`)

### 18. Integratoruitleg

- Importeer `EducationalAccess` van `src.core.models.foundation_content`.
- Genereer codes via `EducationalAccess(tenant_id=..., code="...", email="...", role="teacher")`.
- Controleer altijd `is_active` en `expires_at` bij code-verificatie.
- Codes zijn globaal uniek; hergebruik over tenants heen is niet mogelijk.

### 19. Trainingssamenvatting

| Veld | Inhoud |
|------|--------|
| Actor | Backend systeem / Edu code-verificatie endpoint |
| Voorwaarde | PostgreSQL bereikbaar, migratie uitgevoerd, tenant bestaat |
| Actie | Maak `EducationalAccess` of verifieer een code |
| Systeemverwerking | SQLAlchemy INSERT of SELECT met RLS-filter; unieke constraint check |
| Succesrespons | Access-record gevonden of succesvol aangemaakt |
| Foutrespons | IntegrityError bij dubbele code; 403 bij inactive/verlopen code |
| Uitzonderingen | Tenant-context ontbreekt: RLS blokkeert alle rijen -> leeg resultaat |

---

## [BE-MDL-015-B] StudyCollection

### 1. Type

SQLAlchemy 2.0 ORM Model (asyncpg-compatibel) -- nieuw model

### 2. Locatie

- Bestandspad: `src/core/models/foundation_content.py`
- Klasse: `StudyCollection`
- Base: `src.core.database.database.Base`

### 3. Gerelateerde flow

- Educatieve content-weergave (toekomstig endpoint)
- Study collection CRUD (toekomstig endpoint)
- Koppeling `StudyCollection` <-> `FoundationContent` (toekomstige many-to-many tabel)

### 4. Doel

Een gecureerde verzameling van lesmaterialen opslaan die gekoppeld is aan een
toegangscode. Gebruikers met een geldige `EducationalAccess` code kunnen de
bijbehorende collectie bekijken.

### 5. Functionele beschrijving

Een `StudyCollection` heeft een naam, optionele beschrijving en een
`access_code`. De `access_code` is dezelfde string als de `code` in
`EducationalAccess`. Wanneer een gebruiker de code invoert, kan het systeem
alle `StudyCollection` records met die `access_code` ophalen binnen de tenant.

### 6. Technische beschrijving

```python
class StudyCollection(Base):
    __tablename__ = "study_collections"
    __table_args__ = (
        Index("idx_sc_tenant_code", "tenant_id", "access_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
```

RLS policy (migratie):
```sql
ALTER TABLE study_collections ENABLE ROW LEVEL SECURITY;
CREATE POLICY study_collections_tenant_isolation
  ON study_collections FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::int);
```

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT of magic-link sessie (endpoint-laag)
- Vereiste rol / scope: endpoint-afhankelijk
- Tenant-isolatie: RLS + NOT NULL tenant_id + ORM hook (ADR-004)
- Feature flag: --

### 8. Request-specificatie

NVT -- dit is een model, geen endpoint.

### 9. Response-specificatie

NVT -- dit is een model, geen endpoint.

### 10. Validaties en constraints

- `tenant_id`: NOT NULL, FK(tenants.id, CASCADE), index
- `name`: `String(200)`, NOT NULL
- `description`: `Text`, nullable
- `access_code`: `String(20)`, NOT NULL, index (niet uniek; meerdere collecties
  kunnen dezelfde code delen voor groepering)

### 11. Business rules

- Meerdere `StudyCollection` records kunnen dezelfde `access_code` hebben
  (1:N relatie van code naar collecties).
- `access_code` moet overeenkomen met een bestaande `EducationalAccess.code`
  binnen dezelfde tenant (applicatie-validatie, geen FK).
- Een collectie kan leeg zijn (nog geen gekoppelde content).

### 12. Afhankelijkheden

- `src.core.database.database.Base`
- PostgreSQL 15+ (RLS)
- `tenants` tabel bestaat (FK)
- Alembic-migratie `20260824_adr029_portal_v1`

### 13. Foutafhandeling

- 500: Database-fout bij ontbrekende migratie
- 400 (endpoint-laag): Ontbrekende `name`

### 14. Transacties en data-integriteit

- Geen FK naar `EducationalAccess`; koppeling is loose op basis van
  `access_code` string-match binnen tenant. Dit voorkomt circular dependencies.
- Downgrade dropt tabel na policy+RLS disable.

### 15. Telemetry / logging / tracing

NVT op model-niveau.

### 16. Caching

NVT.

### 17. Acceptatiecriteria

- [x] `StudyCollection` is importeerbaar vanuit `src.core.models.foundation_content`
- [x] `tenant_id` is NOT NULL
- [x] `name` is NOT NULL
- [x] `access_code` is NOT NULL, geindexeerd
- [x] `description` is nullable
- [x] RLS policy aanwezig in migratie
- [x] Succesvolle creatie getest (`test_study_collection_create`)
- [x] Tenant+access_code index aanwezig (`idx_sc_tenant_code`)

### 18. Integratoruitleg

- Importeer `StudyCollection` van `src.core.models.foundation_content`.
- `access_code` koppelt los aan `EducationalAccess`; controleer in de
  applicatielaag of de code geldig is voordat collecties worden getoond.
- Meerdere collecties kunnen dezelfde `access_code` delen.

### 19. Trainingssamenvatting

| Veld | Inhoud |
|------|--------|
| Actor | Backend systeem / Edu content endpoint |
| Voorwaarde | PostgreSQL bereikbaar, migratie uitgevoerd, geldige access code |
| Actie | Maak `StudyCollection` of haal collecties op bij access code |
| Systeemverwerking | SQLAlchemy SELECT/INSERT met RLS-filter + tenant_id filter |
| Succesrespons | Collectie(s) geretourneerd |
| Foutrespons | Leeg resultaat bij ongeldige tenant of code |
| Uitzonderingen | Geen geldige access code -> lege collectielijst |

---

## Multi-tenant Veiligheid

### RLS policies

Beide tabellen hebben RLS ingeschakeld met het safe NULLIF-pattern (ADR-005):

```sql
-- EducationalAccess
CREATE POLICY educational_access_tenant_isolation
  ON educational_access FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::int);

-- StudyCollection
CREATE POLICY study_collections_tenant_isolation
  ON study_collections FOR ALL
  USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::int);
```

### Tenant-isolatie op model-niveau

- `tenant_id` is NOT NULL op beide modellen.
- De ORM `do_orm_execute` hook (ADR-004) injecteert automatisch een
  `tenant_id = ...` WHERE-clausule voor alle queries op modellen met een
  `tenant_id` kolom.
- `EducationalAccess` heeft GEEN eigen tenant_id-isolatie-uitzondering;
  het is een standalone model met RLS.

### Cross-tenant risico's

| Risico | Mitigatie |
|--------|-----------|
| Code-gokken over tenants | `code` is globaal uniek; tenant-scoped queries + RLS |
| Access_code lekken naar verkeerde tenant | RLS + tenant_id filter in alle queries |
| Educatieve data in DSAR export van verkeerde tenant | `do_orm_execute` hook + RLS |

### Loose koppeling StudyCollection -> EducationalAccess

Er is geen expliciete FK van `StudyCollection.access_code` naar
`EducationalAccess.code`. Dit is bewust:
1. Voorkomt circular dependency tussen tabellen.
2. Staat toe dat collecties worden aangemaakt voordat codes worden uitgedeeld.
3. Maakt het mogelijk om meerdere collecties aan dezelfde code te koppelen.

De applicatie-laag MOET valideren dat `StudyCollection.access_code` overeenkomt
met een bestaande, actieve `EducationalAccess.code` binnen dezelfde tenant.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- `EducationalAccess` bevat de toegangscodes; `StudyCollection` bevat de
  lesmaterialen. De koppeling loopt via `access_code` string-match binnen tenant.
- Genereer eerst een `EducationalAccess` record met code, e-mail en rol.
- Maak daarna een of meer `StudyCollection` records met dezelfde `access_code`.
- Bij code-verificatie: controleer `is_active` en `expires_at` op
  `EducationalAccess`, haal daarna `StudyCollection` records op met dezelfde code.
- Alle queries MOETEN filteren op `tenant_id`; RLS is een safety-net, geen
  vervanging voor applicatie-filters.

---

## Open aannames

- `EducationalAccess.code` is globaal uniek (kolom-niveau unique=True), niet
  alleen per tenant. Dit voorkomt code-conflicten maar beperkt hergebruik van
code-strings over tenants heen.
- `StudyCollection` heeft nog geen FK-veld naar `FoundationContent`; een
  many-to-many koppeltabel volgt in een latere sprint.
- `EducationalRole` dupliceert waarden uit `PortalRole`; dit is bewust omdat
  educatieve rollen mogelijk anders evolueren dan portal-rollen.

## Open vragen

- Moet `StudyCollection` een `created_by` FK naar `PortalUser` krijgen voor
  audit-trail?
- Moet `EducationalAccess` een `used_at` timestamp krijgen voor gebruikstracking?
- Moet de loose `access_code` koppeling vervangen worden door een expliciete
  FK in een toekomstige refactor?

## Risico's

- Loose koppeling `StudyCollection.access_code` -> `EducationalAccess.code`
  biedt geen database-garantie voor referentiele integriteit. Een code kan
  worden verwijderd terwijl collecties er nog naar verwijzen.
- `EducationalAccess.code` globale uniciteit kan schalen tot een bottleneck bij
  massale code-generatie (bijv. voor hele schooldistricten).
- `expires_at` wordt niet automatisch afgedwongen door de database; de
  applicatie moet expliciet controleren.

---

## QA-checks

- [x] Model constraints getest (NOT NULL, defaults, uniekheid)
- [x] Tenant-isolatie op model-niveau bevestigd (RLS + NOT NULL tenant_id)
- [x] Alembic migratie getest (upgrade + downgrade)
- [x] RLS policies geverifieerd in migratie
- [x] Duplicatie-integrity getest (`test_educational_access_duplicate_code_raises`)
- [x] Creatie van beide modellen getest

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle modellen zijn geinventariseerd
- [x] Acceptatiecriteria zijn testbaar
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Multi-tenant veiligheid beschreven
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [ ] Review door reviewer-prompt: (nog uit te voeren)
