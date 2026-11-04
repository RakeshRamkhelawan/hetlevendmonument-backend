# Backend Feature Specification

## Metadata

| Veld | Waarde |
|------|--------|
| Feature ID | BE-MIG-014 |
| Naam | Sprint C datamodel-uitbreiding: visibility, ContentType-uitbreiding, target_age_group |
| Status | In uitvoering |
| Auteur | AI-agent (senior architect-rol) |
| Reviewer | Onafhankelijke review-agent (Gate 2) |
| Datum | 2026-09-10 |
| User story / ticket | ADR-029 audit, bevinding N-2 (`docs/reports/ADR-029_AUDIT_VERIFIED_2026-08-30.md` regels 125-153, voorgeschreven volgorde regels 379-382); architectuur-eisen `docs/adr/029-foundation-portal-architecture.md` regels 191-201 en 212-219 |
| Router / module | `src/core/models/foundation_content.py` (geen router-wijziging) |
| Frontend endpoints | n.v.t. |
| Database tabellen | `foundation_content` (2 nieuwe kolommen + 1 nieuwe enum + 6 nieuwe enum-waarden); migratie nodig: **ja** |
| Versie | 1.0 |

## Doel en scope

### Doel

Het datamodel geschikt maken voor educatieve content vóórdat de edu-endpoints (Sprint D / BE-EP-039) gebouwd kunnen worden. Kern: `edu`-content mag NOOIT in het publieke archief verschijnen; dat vereist een expliciet `visibility`-veld, geen hergebruik van `privacy`.

### In scope

- Nieuwe Postgres-enum `visibility_enum` met waarden `public`, `edu`, `community`.
- Nieuwe kolom `foundation_content.visibility` (`visibility_enum`, NOT NULL, server_default `'public'`), met backfill vanuit `privacy` (PUBLIC → public, COMMUNITY → community).
- Zes nieuwe waarden op `content_type_enum`: `video`, `educational_workbook`, `educational_video`, `teacher_guide`, `event_report`, `art_documentation`.
- Nieuwe kolom `foundation_content.target_age_group` (String(50), nullable).
- ORM-model bijwerken (`ContentType`, nieuwe `Visibility`-enum, kolommen).
- Migratie met upgrade- én downgrade-roundtrip getest op echte Postgres.
- Unit-tests voor model-defaults en enum-waarden.
- Registratie in `docs/backend/features/ID-REGISTRY.md`.

### Out of scope

- Query-wijzigingen in bestaande endpoints (content.py, map.py) — Sprint D schakelt filters over op `visibility`.
- Verwijdering of deprecatie van de `privacy`-kolom (latere opruim-migratie).
- Koppeling `StudyCollection` ↔ `FoundationContent` (hoort bij Sprint D leerling-overzicht).
- De edu-endpoints zelf (BE-EP-039).
- `metadata_` JSONB-validatie per content-type (ADR-029 regels 212-219) — Sprint D.

## Ontwerpbeslissingen

| # | Beslissing | Reden |
|---|-----------|-------|
| O1 | Aparta `visibility_enum` (public/edu/community) naast bestaande `privacy_enum`; `privacy` blijft in Sprint C ongemoeid | De audit (N-2) eist een expliciet visibility-veld; `edu` is een publicatie-kanaal, geen privacy-niveau. Big-bang-vervanging van `privacy` in dezelfde migratie zou alle bestaande endpoints in één keer raken — regressierisico zonder noodzaak (Karpathy: surgical changes). |
| O2 | Backfill `visibility` vanuit `privacy` (PUBLIC→public, COMMUNITY→community); server_default `'public'` | Bestaande rijen moeten na de migratie hetzelfde zichtbaarheidsgedrag houden. Default `'public'` is de veilige, huidige standaard. |
| O3 | Enum-waarden toevoegen in een `autocommit_block()`, kolommen daarna in de gewone transactie | Postgres staat gebruik van een nieuwe enum-waarde niet toe in dezelfde transactie als het `ALTER TYPE ... ADD VALUE` (audit regels 150-153). Met autocommit-blok + `IF NOT EXISTS` is de migratie idempotent en herhaalbaar. |
| O4 | `target_age_group` als `String(50)` nullable, geen enum | Leeftijdsgroepen verschillen per stichting en evolueren; een Postgres-enum zou elke nieuwe groep een migratie maken. Validatie van toegestane waarden hoort bij de metadata-schema's in Sprint D. |
| O5 | Exact de zes ContentType-waarden uit de audit | `video`, `educational_workbook`, `educational_video`, `teacher_guide`, `event_report`, `art_documentation` (audit regels 141-146). Geen extra waarden verzinnen. |
| O6 | `Visibility` Python-enum met lowercase values via `values_callable`, zelfde patroon als `EducationalRole` | Consistent met BE-MIG-013-beslissing; Postgres-enum-waarden blijven lowercase (voorkomt de VISITOR/case-bug uit 20260824). |
| O7 | Index op `(tenant_id, visibility, status)` toevoegen | De edu-lijstquery (Sprint D) filtert precies op deze drie; nu aanleggen voorkomt een extra migratie in Sprint D. |

## Build summary

### Nieuw gebouwd

- `src/alembic/versions/20260910_adr029_sprint_c_datamodel.py` — migratie (enum + waarden + kolommen + backfill + index).
- `tests/unit/models/` of bestaande testlocatie: model-tests voor nieuwe velden.
- Migratie-roundtrip-test (upgrade + downgrade) tegen echte Postgres.

### Gewijzigd

- `src/core/models/foundation_content.py` — `ContentType` +6 waarden; nieuwe `Visibility`-enum; kolommen `visibility` en `target_age_group` op `FoundationContent`.
- `docs/backend/features/ID-REGISTRY.md` — regel voor BE-MIG-014.

### Verwijderd

- Niets.

### Beïnvloede bestaande flows

- Geen runtime-flow wijzigt: bestaande endpoints lezen/schrijven `visibility` nog niet. Default `'public'` + backfill garanderen identiek gedrag.

## Migratie-flow

1. `autocommit_block()`: `CREATE TYPE visibility_enum` (via SQLAlchemy `ENUM(...).create(..., checkfirst=True)`) — OF in autocommit `CREATE TYPE IF NOT EXISTS`-equivalent; daarna in hetzelfde autocommit-blok `ALTER TYPE content_type_enum ADD VALUE IF NOT EXISTS '<waarde>'` voor elk van de 6 waarden.
2. Normale transactie: `ADD COLUMN visibility visibility_enum NOT NULL DEFAULT 'public'`, `ADD COLUMN target_age_group VARCHAR(50) NULL`.
3. Backfill: `UPDATE foundation_content SET visibility = CASE privacy::text WHEN 'PUBLIC' THEN 'public' WHEN 'COMMUNITY' THEN 'community' ELSE 'public' END` (defensieve cast, zelfde patroon als BE-MIG-013; rowcount loggen/checken).
4. Index `idx_fc_tenant_visibility_status` aanmaken.
5. Downgrade: index en kolommen droppen; enum-waarden laten staan (Postgres kan enum-waarden niet verwijderen; documenteren), `visibility_enum` droppen.
6. `alembic -c src/alembic.ini heads` toont na afloop exact 1 head; down_revision = `20260909_adr029_edu_alignment`.

### Testplan

**Unit (offline):**
- `ContentType` bevat de 6 nieuwe waarden met correcte string-values.
- `Visibility`-enum: waarden `public`/`edu`/`community`, lowercase.
- Model-instantie zonder expliciete visibility krijgt default (Python-side of server_default gedocumenteerd).

**Integratie / migratie (echte Postgres, docker pgvector):**
- `upgrade head` slaagt vanaf `20260909_adr029_edu_alignment`.
- Na upgrade: kolommen bestaan, enum bevat nieuwe waarden, backfill correct (testrij met privacy=COMMUNITY → visibility=community).
- `downgrade -1` + opnieuw `upgrade head` slaagt (roundtrip).
- `alembic heads` = exact 1.

## Open aannames

- Bestaande rijen: geen enkele rij heeft nu edu-intentie, dus backfill naar public/community dekt alles.
- `visibility_enum` als losse enum (niet hergebruik van `privacy_enum`) is bewust: anders zou `ALTER TYPE privacy_enum ADD VALUE 'edu'` het oude veld semantisch vervuilen.

## Definition of Done

- [ ] Migratie upgrade + downgrade + upgrade groen op echte Postgres
- [ ] Backfill geverifieerd met testdata
- [ ] `alembic heads` toont exact 1 head
- [ ] Unit-tests groen (`tests/unit/...` gericht, `-n 4`)
- [ ] ruff groen op gewijzigde bestanden; mypy op gewijzigde bestanden groen
- [ ] Spec + review aanwezig; review APPROVED (incl. Devil's Advocate-sectie)
- [ ] ID-REGISTRY.md bijgewerkt

---

## Trainingssamenvatting

- **Actor:** Databasebeheerder of geautomatiseerde CI/CD deployment pipeline tijdens schema-migratie.
- **Voorwaarde:** PostgreSQL database met migratie 20260909_adr029_edu_alignment reeds toegepast (single head keten).
- **Actie:** Uitvoeren van alembic -c src/alembic.ini upgrade head (migratie 20260910_adr029_sprint_c_datamodel).
- **Systeemverwerking:** Alembic maakt de nieuwe PostgreSQL enum visibility_enum aan buiten transactieblokken, voegt kolommen visibility en target_age_group toe aan tabel foundation_content, voert een defensieve backfill query uit van bestaande privacy waarden naar visibility, creeert de index idx_fc_tenant_visibility_status, en voegt de nieuwe educatieve content-type waarden toe aan content_type_enum.
- **Succesrespons:** Alembic migreert succesvol naar de nieuwe head revision zonder dataverlies of lock contention; alembic heads toont exact 1 head.
- **Foutrespons:** Alembic upgrade fout indien afhankelijkheden ontbreken, ongeldige database-rechten, of conflicterende enum definities.
