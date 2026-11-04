# Backend Feature Specification -- BE-MDL-014

## Metadata

- Feature ID: BE-MDL-014
- Feature naam: PortalUser Role Enum + Consent Velduitbreiding
- Status: IMPLEMENTED
- Auteur: Backend Documentatie Agent
- Reviewer: (te reviewen)
- Datum: 2026-08-24
- Gerelateerde user story / ticket: ADR-029 Foundation Portal -- Dag 1
- Gerelateerde router / module: `src/core/models/foundation_content.py`
- Gerelateerde frontend endpoints: (frontend spec volgt in aparte sprint)
- Gerelateerde database tabellen: `portal_users`
- Versie: 1.0

---

## Doel en scope

### Doel

Uitbreiden van het `PortalUser` model met een `role` enum (`PortalRole`) voor
RBAC binnen het Foundation Portal, plus GDPR-compliant consent-tracking
(`email_verified`, `consent_given`, `consent_given_at`). Dit maakt
rolgebaseerde toegangscontrole en expliciete gebruikerstoestemming mogelijk
voor AI-curatie en content-publicatie.

### In scope

- `PortalRole` enum: ADMIN, CURATOR, TEACHER, STUDENT, VISITOR
- `PortalUser`: +role (enum, NOT NULL, default=VISITOR), +email_verified,
  +consent_given, +consent_given_at
- Alembic migratie `20260824_adr029_portal_v1` (sectie 3)
- Unieke tenant+email index (`idx_pu_tenant_email`)

### Out of scope

- API-endpoints voor rolwijziging (toekomstige sprint)
- Consent-vereiste workflow in frontend (ADR-029 frontend sprint)
- Magic-link verificatie-flow (bestaande functionaliteit, niet gewijzigd)
- Integratie met Council governance voor rolwijzigingen

---

## Build summary

- Nieuw gebouwd:
  - `PortalRole` enum (5 waarden)
  - `role`, `email_verified`, `consent_given`, `consent_given_at` velden op `PortalUser`
- Gewijzigd:
  - `src/core/models/foundation_content.py` -- 4 velden toegevoegd
  - `src/alembic/versions/20260824_adr029_portal_v1.py` -- migratie met server defaults
- Verwijderd: --
- Beinvloede bestaande flows:
  - `PortalUser` instantiatie in bestaande tests (backward-compatibel: `role`
    heeft server_default="visitor", boolean velden hebben server_default="false")

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-MDL-014 | PortalUser role + consent | Model | `src/core/models/foundation_content.py` | Wijziging | Magic-link login, content upload, consent flow |
| BE-MIG-029-001 | adr029_portal_v1 (sectie 3) | Migratie | `src/alembic/versions/20260824_adr029_portal_v1.py` | Nieuw | -- |

---

## Detaildocumentatie per artefact

---

## [BE-MDL-014] PortalUser -- Role enum + Consent velden

### 1. Type

SQLAlchemy 2.0 ORM Model (asyncpg-compatibel) -- velduitbreiding op bestaand model

### 2. Locatie

- Bestandspad: `src/core/models/foundation_content.py`
- Klasse: `PortalUser`
- Enum: `PortalRole`
- Base: `src.core.database.database.Base`

### 3. Gerelateerde flow

- Magic-link login flow (bestaand)
- Content upload flow (rol bepaalt permissies)
- GDPR consent-verzameling bij registratie
- Admin/curator dashboard (rol-gefilterde weergave)

### 4. Doel

Portal-gebruikers krijgen een expliciete rol die hun permissies binnen de tenant
bepaalt. Consent-tracking voldoet aan GDPR Art. 7 (bewijs van toestemming) en
ondersteunt de AI Act transparency requirements (ADR-031).

### 5. Functionele beschrijving

Elke `PortalUser` heeft een `PortalRole` die bepaalt welke acties de gebruiker
mag uitvoeren:
- **ADMIN** -- Volledig beheer van portal content, gebruikers en instellingen
- **CURATOR** -- Content goedkeuren, afwijzen, modereren; takedown-afhandeling
- **TEACHER** -- Educatieve content beheren; toegang tot study collections
- **STUDENT** -- Content bekijken binnen educatieve collecties; eigen content uploaden
- **VISITOR** -- Basis browsen; geen upload zonder rol-escalatie

`email_verified` geeft aan of het e-mailadres is geverifieerd via magic-link.
`consent_given` en `consent_given_at` vormen het GDPR-toestemmingsbewijs.

### 6. Technische beschrijving

```python
class PortalRole(str, enum.Enum):
    ADMIN = "admin"
    CURATOR = "curator"
    TEACHER = "teacher"
    STUDENT = "student"
    VISITOR = "visitor"

class PortalUser(Base):
    # ... bestaande velden ...

    role: Mapped[PortalRole] = mapped_column(
        PGEnum(PortalRole, name="portal_role_enum"),
        default=PortalRole.VISITOR,
        nullable=False,
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    consent_given: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    consent_given_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

Indexen:
- `idx_pu_tenant_email` -- unieke samengestelde index op (tenant_id, email)

Migratie-upgrade voegt de kolommen toe met server defaults:
- `role`: server_default="visitor"
- `email_verified`: server_default="false"
- `consent_given`: server_default="false"
- `consent_given_at`: geen default (nullable)

Downgrade dropt de 4 kolommen.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: JWT of magic-link sessie (endpoint-laag)
- Vereiste rol / scope: endpoint-afhankelijk; model heeft geen eigen auth
- Tenant-isolatie: `tenant_id` NOT NULL + FK CASCADE + ORM hook (ADR-004) + RLS (ADR-005)
- Feature flag: --

### 8. Request-specificatie

NVT -- dit is een model, geen endpoint.

### 9. Response-specificatie

NVT -- dit is een model, geen endpoint.

### 10. Validaties en constraints

- `role`: `portal_role_enum` (PostgreSQL ENUM), NOT NULL, default=VISITOR
- `email_verified`: `Boolean`, NOT NULL, default=False
- `consent_given`: `Boolean`, NOT NULL, default=False
- `consent_given_at`: `DateTime(timezone=True)`, nullable
- `tenant_id` + `email` uniek samengesteld (bestaand, onveranderd)
- `display_name`: `String(120)`, nullable (bestaand)
- `is_verified`: `Boolean`, default=False, NOT NULL (bestaand; semantisch overlappend
  met `email_verified` maar bewaard voor backward-compatibiliteit)

### 11. Business rules

- Default rol is VISITOR. Expliciete roltoewijzing vereist admin-interventie of
  een invite-flow (buiten scope).
- `consent_given` kan alleen `True` worden als `email_verified` ook `True` is
  (applicatieregel, niet database-constraint).
- `consent_given_at` moet worden gezet op het moment dat `consent_given` naar
  `True` wordt gezet (applicatieregel).
- Een gebruiker kan meerdere `MagicLinkToken` records hebben (1:N relatie).

### 12. Afhankelijkheden

- `src.core.database.database.Base`
- PostgreSQL 15+ (ENUM, RLS)
- `tenants` tabel bestaat (FK)
- Alembic-migratie `20260824_adr029_portal_v1`

### 13. Foutafhandeling

- 500: `IntegrityError` bij dubbele (tenant_id, email) combinatie (bestaand gedrag)
- 500: Database-fout bij ontbrekende migratie
- 400 (endpoint-laag): Ongeldige `PortalRole`-waarde (string buiten enum)
- 422 (endpoint-laag): `consent_given=True` zonder `email_verified=True`

### 14. Transacties en data-integriteit

- Server defaults zorgen dat bestaande rijen na migratie geldige waarden krijgen:
  alle bestaande gebruikers worden VISITOR met onverifieerd e-mail en geen consent.
- `consent_given_at` is NULL totdat expliciet consent wordt gegeven.
- Downgrade dropt kolommen in omgekeerde volgorde (constraint-safe).

### 15. Telemetry / logging / tracing

NVT op model-niveau. Endpoints loggen `tenant_id` + `portal_user_id` + `role`
bij mutaties.

### 16. Caching

NVT.

### 17. Acceptatiecriteria

- [x] `PortalRole` enum bevat 5 waarden: ADMIN, CURATOR, TEACHER, STUDENT, VISITOR
- [x] `role` is NOT NULL met default=VISITOR (server_default="visitor")
- [x] `email_verified` is NOT NULL met default=False (server_default="false")
- [x] `consent_given` is NOT NULL met default=False (server_default="false")
- [x] `consent_given_at` is nullable DateTime(tz)
- [x] Migratie-upgrade voegt velden toe zonder data-verlies; bestaande rijen
  krijgen default-waarden
- [x] Migratie-downgrade verwijdert de 4 kolommen
- [x] Bestaande `PortalUser` instantiatie zonder rol/consent werkt (defaults)
- [x] `PortalUser` met expliciete rol kan succesvol worden aangemaakt (test:
  `test_portal_user_with_role`)
- [x] Ongeldige `PortalRole`-string wordt afgewezen (test:
  `test_portal_user_invalid_role_rejected`)

### 18. Integratoruitleg

- Importeer `PortalUser` en `PortalRole` van `src.core.models.foundation_content`.
- Rol-assignatie gebeurt expliciet; default is `VISITOR`.
- Consent-tracking vereist dat `email_verified=True` voordat `consent_given=True`
  wordt gezet; `consent_given_at` moet op dat moment worden gevuld.
- De (tenant_id, email) combinatie blijft uniek; dit voorkomt dubbele accounts
  binnen een tenant.

### 19. Trainingssamenvatting

| Veld | Inhoud |
|------|--------|
| Actor | Backend systeem / Portal registratie endpoint |
| Voorwaarde | PostgreSQL bereikbaar, Alembic migratie uitgevoerd |
| Actie | Maak of wijzig `PortalUser` met rol en consent-status |
| Systeemverwerking | SQLAlchemy INSERT/UPDATE; ENUM-validatie door PostgreSQL |
| Succesrespons | PortalUser-object met rol en consent-velden |
| Foutrespons | IntegrityError bij dubbele e-mail; ValueError bij ongeldige rol |
| Uitzonderingen | Migratie niet uitgevoerd: kolommen ontbreken -> 500 bij INSERT |

---

## GDPR / AI Act Implicaties

### GDPR Art. 7 -- Bewijs van toestemming

- `consent_given` (boolean) + `consent_given_at` (timestamp) vormen samen een
  audit-trail voor expliciete toestemming.
- Aanbeveling: log ook `consent_ip` en `consent_user_agent` bij consent-moment
  (vergelijkbaar met `NewsletterSubscription`).
- `consent_given` default=False voldoet aan de "opt-in" vereiste; gebruikers
  worden nooit impliciet als toestemmend beschouwd.

### GDPR Art. 17 -- Recht op vergetelheid

- `PortalUser` heeft `cascade="all, delete-orphan"` op `MagicLinkToken`.
- Bij verwijdering van een gebruiker worden gekoppelde tokens automatisch
  verwijderd.
- Content (`FoundationContent.uploader_id` met `ondelete="SET NULL"`) wordt
  geanonimiseerd, niet verwijderd.

### AI Act 2026 -- Transparency

- Rol-tracking maakt het mogelijk om te rapporteren WELKE rol een gebruiker had
  toen AI-curatie of content-moderatie plaatsvond.
- `consent_given` is vereist voor AI-verwerking van persoonsgegevens
  (bijv. AI-tagging van geuploade content met persoonlijke verhalen).
- De Council (ADR-027) kan `consent_given` als governance-criterium gebruiken
  bij voorstellen die PII bevatten.

### Data-retentie

- `consent_given_at` moet worden meegenomen in de DSAR-export.
- Bij intrekking van toestemming: `consent_given=False` zetten; `consent_given_at`
  behouden als audit-trail (of expliciet wissen per tenant-policy).

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- `PortalUser` heeft vanaf deze versie een verplichte `role` (default: VISITOR).
- Alle bestaande gebruikers krijgen na migratie automatisch rol=VISITOR.
- Consent dient expliciet te worden verzameld via de frontend voordat
  `consent_given=True` wordt gezet.
- Rol-wijzigingen (bijv. VISITOR -> STUDENT via educatieve access code) worden
  via het `EducationalAccess` model afgehandeld, niet direct op `PortalUser`.

---

## Open aannames

- `is_verified` (bestaand) en `email_verified` (nieuw) zijn semantisch gelijk;
  `email_verified` is de canonieke naam voor nieuwe code. `is_verified` blijft
  bestaan voor backward-compatibiliteit.
- Rol-wijzigingen gebeuren via admin-actie of educatieve invite-flow, niet via
  zelfservice (applicatieregel).
- `consent_given=True` impliceert dat de gebruiker de privacy policy en
  AI-gebruiksvoorwaarden heeft geaccepteerd (juridische tekst buiten scope).

## Open vragen

- Moet `is_verified` worden gemarkeerd als deprecated ten gunste van `email_verified`?
- Moet een consent-intrekking (`consent_given=False`) automatisch AI-verwerking
  blokkeren voor bestaande content van deze gebruiker?

## Risico's

- Bestaande gebruikers krijgen na migratie rol=VISITOR. Dit kan onverwachte
  permissie-daling veroorzaken als er voorheen impliciet hogere permissies waren.
  Aanbeveling: na migratie admin-script draaien om bekende curators/admins te
  promoveren.
- `consent_given` en `is_verified` zijn gescheiden velden; inconsistentie kan
  ontstaan als de applicatie beide velden niet synchroon houdt.

---

## QA-checks

- [x] Model constraints getest (NOT NULL, defaults, ENUM-waarden)
- [x] Tenant-isolatie op model-niveau bevestigd (RLS + NOT NULL tenant_id)
- [x] Alembic migratie getest (upgrade + downgrade)
- [x] Backward-compatibiliteit: oude instantiatie met defaults werkt
- [x] Rol-instantiatie getest (`test_portal_user_with_role`)
- [x] Ongeldige rol-enum getest (`test_portal_user_invalid_role_rejected`)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle modellen zijn geinventariseerd
- [x] Acceptatiecriteria zijn testbaar
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] GDPR/AI Act implicaties beschreven
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [ ] Review door reviewer-prompt: (nog uit te voeren)
