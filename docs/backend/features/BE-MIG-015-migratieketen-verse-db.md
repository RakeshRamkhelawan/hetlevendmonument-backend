# Backend Feature Specification

## Metadata

- Feature ID: BE-MIG-015
- Feature naam: Migratieketen draait vanaf een lege database naar head (edu_alignment defensief)
- Status: Gebouwd en geverifieerd; review via reviewer-prompt volgt (Gate 2)
- Auteur: implementatie-agent sprint "Week 1 markt-blokkers", worktree hlm-wk1-migratieketen
- Reviewer: (nog toe te wijzen)
- Datum: 2026-09-24
- Gerelateerde user story / ticket: Taak D "Week 1 markt-blokkers"; markt-review 2026-09-24 (database.md)
- Gerelateerde router / module: `src/alembic/versions/20260909_adr029_edu_alignment.py`
- Gerelateerde frontend endpoints: geen
- Gerelateerde database tabellen: `educational_access`, `study_collections`, `newsletter_subscriptions` (enum)
- Versie: 1.0

---

## Doel en scope

### Doel

`alembic -c src/alembic.ini upgrade head` moet vanaf een LEGE PostgreSQL naar head
draaien. Gemeten defect (markt-review 2026-09-24, gereproduceerd 2026-09-24 op een
verse PostgreSQL 15.18, wegwerp-database op de testserver poort 5455):

```
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.DuplicateColumn)
column "code_hash" of relation "educational_access" already exists
[SQL: ALTER TABLE educational_access RENAME code TO code_hash]
```

Zonder deze fix kan geen nieuwe klantomgeving, tweede regio of calamiteitherstel
worden opgebouwd -- een markt-blokker.

### In scope

- `20260909_adr029_edu_alignment` defensief/idempotent maken (upgrade EN downgrade).
- Alle overlaps tussen `20260917_kolomdrift` en `20260909_adr029_edu_alignment`.
- Rode-test-eerst: nieuwe integratietest die verse upgrade + eindtoestand + roundtrip
  bewijst op een echte lege Postgres.
- Verificatie op echte Postgres: verse upgrade head, roundtrip van de geraakte
  migratie, roundtrip DOOR kolomdrift's downgrade heen.

### Out of scope

- `alembic check`-drift (516 verschillen) -- ADR-036 OP-150.
- Constraint-naamgeving harmoniseren tussen migratiepaden en `create_all`
  (bewust, zie "Business rules").
- Andere migraties dan edu_alignment; kolomdrift blijft ongemoeid (zie strategie).
- Volledige downgrade-naar-base van alle 100+ migraties (pre-existing risico's
  daarin zijn geen onderdeel van deze bevinding).

---

## Overlap-inventaris (gemeten, niet vermoed)

Ketenvolgorde sinds de herkoppeling van 2026-09-18 (`alembic history`):

```
20260915_rls_rest -> 20260917_kolomdrift (branchpoint)
    tak A: 20260909_adr029_edu_alignment -> 20260910_adr029_sprint_c_datamodel
           -> 20260915_adr029_audit_hardening
    tak B: 20260920_tenant_llm
-> 20260924_merge_adr029_tenant_llm_heads (head)
```

Overlaps tussen kolomdrift (draait eerst) en edu_alignment (draait daarna):

| Object | Kolomdrift maakt | Edu_alignment deed (oud) | Gevolg op verse DB |
| --- | --- | --- | --- |
| `educational_access.code_hash` String(64) NOT NULL | ADD COLUMN | RENAME `code` -> `code_hash` | DuplicateColumn (fataal) |
| unieke sleutel op code_hash | `uq_educational_access_code_hash` | `educational_access_code_hash_key` | dubbele unieke sleutel |
| `study_collections.educational_access_id` NOT NULL | ADD COLUMN | ADD COLUMN | DuplicateColumn (fataal) |
| FK naar educational_access.id | `fk_study_collections_educational_access_id` | `study_collections_educational_access_id_fkey` | dubbele FK |
| index op de FK-kolom | `ix_study_collections_educational_access_id` | zelfde naam | DuplicateRelation (fataal) |

Gecontroleerd en GEEN overlap: `newsletter_status_enum` (alleen edu_alignment),
`portal_role_enum` / `educational_role_enum` (model-side values_callable, geen DDL),
`20260910_adr029_sprint_c_datamodel` (raakt de tabellen niet),
`20260915_adr029_audit_hardening` (alleen FORCE ROW LEVEL SECURITY op beide tabellen).

## Gekozen strategie en bewijs

**Keuze: de LATER draaiende migratie (edu_alignment) defensief/idempotent gemaakt;
kolomdrift is NIET bijgesneden.**

Redenering (senior-besluit, zoals de opdracht vraagt):

1. Kolomdrift heeft aantoonbaar gedraaid op staging: zijn eigen docstring legt
   rijtellingen op staging vast (2026-09-17) en de keten-guard
   (`KNOWN_KOLOMMEN_ZONDER_MIGRATIE` in
   tests/integration/database/test_the_chain_builds_the_whole_schema.py) is sinds
   die dag leeg. Die migratie herschrijven laat de bestandinhoud afwijken van wat
   er gedraaid heeft -- precies wat .claude/rules/database.md verbiedt.
2. Edu_alignment heeft in zijn huidige ketenpositie NOOIT ergens succesvol
   gedraaid:
   - verse database: faalt (gereproduceerd, zie boven);
   - staging: kolomdrift's docstring meet 2026-09-17 dat staging `code_hash`
     miste, dus edu_alignment had daar toen niet gedraaid; na de herkoppeling
     (2026-09-18) kan hij er alleen maar falen (zelfde DuplicateColumn);
   - productie: niet ingericht sinds 2026-05-11, de migratie is van 2026-09-09;
   - een database die hem in de OUDE positie (down_revision
     20260716_backfill_prana_budgets, voor 2026-09-18) heeft toegepast, draagt de
     revisie-id al in alembic_version en voert hem nooit opnieuw uit.
3. Een NIEUWE migratie bovenop de keten kan dit defect niet repareren: de keten
   sterft IN edu_alignment en bereikt een nieuwe kop nooit. Aanpassen van
   edu_alignment is daarom de enige werkende route; database.md's
   "never modify"-regel beschermt omgevingen die een migratie al hebben gedraaid
   en die zijn er hier niet (punt 2).
4. Kolomdrift bijsnijden (de alternatieve route uit de opdracht) vereist bewijs
   dat kolomdrift NOOIT met die kolommen heeft gedraaid; dat bewijs is er niet
   (punt 1), dus die route valt af.

Bronnen voor het patroon (verplichte research):

- Alembic changelog 1.16.0 -- `add_column(if_not_exists)` /
  `drop_column(if_exists)` / `drop_constraint(if_exists)` bestaan pas sinds 1.16;
  dit project pint 1.13.1, dus introspectie + raw SQL IF EXISTS:
  https://alembic.sqlalchemy.org/en/latest/changelog.html
- Alembic Operation Reference (ops, offline/online gedrag):
  https://alembic.sqlalchemy.org/en/latest/ops.html
- Gevestigde praktijk voor het hier relevante geval (kolom kan al bestaan):
  introspecteer via `sa.inspect(op.get_bind()).get_columns(...)` en pas
  conditioneel toe; fouten stil onderdrukken is expliciet GEEN optie omdat dat de
  transactie laat terugrollen zonder alembic_version-update:
  https://stackoverflow.com/questions/24082542/check-if-a-table-column-exists-in-the-database-using-sqlalchemy-and-alembic

---

## Build summary

- Nieuw gebouwd: `tests/integration/foundation/test_migratieketen_verse_db.py`
  (6 tests: verse upgrade naar head, eindtoestand educational_access /
  study_collections, roundtrip edu_alignment).
- Gewijzigd: `src/alembic/versions/20260909_adr029_edu_alignment.py` -- upgrade en
  downgrade defensief; module-docstring legt de redenering vast. Revision-id en
  down_revision ongewijzigd (geen nieuwe migratie, keten ongewijzigd, pin in
  tests/unit/database/test_agentic_alembic_chain_complete.py blijft correct).
- Verwijderd: niets.
- Beinvloede bestaande flows: elke `alembic upgrade head` op een database die
  edu_alignment nog niet heeft toegepast (verse omgevingen, staging).

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-MIG-015 | edu_alignment defensief/idempotent | Alembic-migratie | `src/alembic/versions/20260909_adr029_edu_alignment.py` | Wijziging | verse omgeving-provisioning |
| BE-MIG-015-T1 | verse-keten integratietest | Test | `tests/integration/foundation/test_migratieketen_verse_db.py` | Nieuw | CI/regressie-bewaking |

---

## Detaildocumentatie per artefact

## [BE-MIG-015] Migratieketen verse database -- edu_alignment defensief

### 1. Type

- Alembic-migratie (bestaande revisie, defensief herschreven)

### 2. Locatie

- Bestandspad: `src/alembic/versions/20260909_adr029_edu_alignment.py`
- Functies: `upgrade()`, `downgrade()`, helpers `_kolommen`,
  `_constraint_bestaat`, `_index_bestaat`, `_fk_op_kolom`,
  `_unieke_constraints_op_kolom`, `_is_offline`, pad-functies
  `_educational_access_rename_pad`, `_educational_access_verwijder_code`,
  `_educational_access_eindsleutels_verzekeren`, `_study_collections_fk_pad`,
  `_study_collections_online`

### 3. Gerelateerde flow

- Provisioning van elke nieuwe PostgreSQL-omgeving via de migratieketen.

### 4. Doel

- De keten van leeg naar head laten slagen, met een eindtoestand die exact
  overeenkomt met de ORM-modellen, ongeacht welke van de reele
  voorgeschiedenissen de database heeft.

### 5. Functionele beschrijving

- De migratie kijkt eerst welke kolommen er staan voordat hij iets wijzigt.
  Staat het oude plaintext-spoor (`code`, `access_code`) er nog naast de nieuwe
  kolommen, dan wordt alleen dat spoor opgeruimd. Ontbreken de nieuwe kolommen,
  dan gebeurt de oude rename/introductie alsnog. Is alles al aligned, dan wordt
  alleen aangevuld wat ontbreekt.

### 6. Technische beschrijving

- Offline (`--sql`): geen inspectie mogelijk; het oorspronkelijke script wordt
  blind gegenereerd (gepinde strings in
  `tests/unit/test_be_mig_013_offline_sql.py` blijven byte-identiek aanwezig;
  gemeten: 5 passed). Offline-detectie via
  `sqlalchemy.engine.mock.MockConnection` (zelfde patroon als
  20260810b_audit_chain_anchors; `MigrationContext.is_offline_mode` bestaat niet
  op alembic 1.13.1 -- gemeten als AttributeError).
- Online educational_access:
  - `code` EN `code_hash` aanwezig (de werkelijke keten post-kolomdrift):
    `DROP CONSTRAINT IF EXISTS educational_access_code_key`, defensieve lookup
    voor afwijkend benoemde unieke constraints op `code`,
    `DROP INDEX IF EXISTS idx_ea_tenant_code`, `DROP COLUMN code`.
  - alleen `code`: het oorspronkelijke rename-pad.
  - daarna altijd: unieke sleutel op code_hash en composite unique index
    `idx_ea_tenant_code` op (tenant_id, code_hash) aanmaken ALS ze ontbreken.
- Online study_collections:
  - `access_code` aanwezig: `DROP INDEX IF EXISTS idx_sc_tenant_code` en
    `ix_study_collections_access_code`, dan `DROP COLUMN access_code`.
  - `educational_access_id` afwezig: ADD COLUMN NOT NULL (alleen veilig op lege
    tabel; de count-checks in stap 2 van de upgrade dwingen dat af en falen luid
    onder niet-eigenaar+RLS).
  - FK op educational_access_id aanmaken ALS er geen enkele FK op die kolom
    bestaat (naam-onafhankelijke check); model-index en `idx_sc_tenant_code`
    idem.
- Downgrade: zet de toestand van VOOR edu_alignment terug, en dat is sinds
  2026-09-18 de toestand NA kolomdrift. Kolomdrift's objecten (code_hash,
  educational_access_id, uq_, fk_, ix_) worden met rust gelaten -- kolomdrift's
  eigen downgrade verwacht ze onder zijn eigen namen en ruimt ze zelf op. Alleen
  `code` en `access_code` met hun sleutels/indexen komen terug. Alleen
  uitvoerbaar op lege tabellen (NOT NULL-kolommen zonder default).

### 7. Zichtbaarheids- en toegangsregels

- Vereist tabel-eigenaar of RLS-bypass-rol voor de DELETE's (ongewijzigd,
  count-checks maken een stille no-op een harde fout).

### 13. Foutafhandeling

- Niet-lege tabellen: harde RuntimeError met tabelnaam en rijtelling
  (ongewijzigd).
- Downgrade op gevulde tabellen: faalt luid op NOT NULL zonder default
  (fail-secure, gedocumenteerd in de migratie-docstring).

### 14. Transacties en data-integriteit

- Transactionele DDL (PostgreSQL): een fout rolt de hele revisie terug;
  alembic_version blijft consistent.

### 17. Acceptatiecriteria

- `alembic upgrade head` op een verse PostgreSQL slaagt; alembic_version =
  20260924_merge_adr029_tenant_llm_heads. [gemeten: GROEN]
- educational_access bevat `code_hash` varchar(64) NOT NULL en GEEN `code`;
  precies een unieke sleutel op code_hash; `idx_ea_tenant_code` UNIQUE op
  (tenant_id, code_hash). [gemeten: GROEN]
- study_collections bevat `educational_access_id` integer NOT NULL met FK naar
  educational_access.id en GEEN `access_code`; indexen
  `ix_study_collections_educational_access_id` en `idx_sc_tenant_code` op
  (tenant_id, educational_access_id). [gemeten: GROEN]
- Roundtrip: downgrade naar 20260917_kolomdrift zet `code`/`access_code` terug
  naast kolomdrift's kolommen; upgrade head herstelt de eindtoestand.
  [gemeten: GROEN]
- Downgrade naar 20260915_rls_rest (door kolomdrift's downgrade heen) en terug
  naar head slaagt -- bewijs dat kolomdrift zijn eigen objecten terugvindt.
  [gemeten: GROEN]
- `alembic heads` = exact 1 head. [gemeten: GROEN]
- Offline-SQL-test (BE-MIG-013) blijft groen zonder te skippen.
  [gemeten: 5 passed]
- Keten-pin-test ongewijzigd groen (geen nieuwe migratie). [gemeten: 5 passed]

### 19. Trainingssamenvatting

- Actor: platform-operator / CI die een nieuwe omgeving provisioneert.
- Voorwaarde: lege PostgreSQL 15+ en deze migratieketen.
- Actie (request): `alembic -c src/alembic.ini upgrade head`.
- Systeemverwerking: kolomdrift voegt code_hash/educational_access_id toe;
  edu_alignment ruimt de plaintext-restkolommen op en verzekert sleutels/indexen.
- Succesrespons: alembic_version op de merge-head; schema matcht de modellen.
- Foutrespons: niet-lege edu-tabellen onder niet-eigenaar -> harde fout met
  rijtelling.
- Uitzonderingen: downgrade vereist lege edu-tabellen (TRUNCATE-instructie in de
  migratie-docstring).

---

## Gemeten verificatie-output (2026-09-24, PostgreSQL 15.18, poort 5455)

Baseline VOOR de fix (wegwerp-database `hlm_wk1_baseline`):

```
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.DuplicateColumn)
column "code_hash" of relation "educational_access" already exists
[SQL: ALTER TABLE educational_access RENAME code TO code_hash]
```

Nieuwe test VOOR de fix: 6 errors (fixture faalt op returncode != 0) -- bewezen rood.

NA de fix:

```
tests/integration/foundation/test_migratieketen_verse_db.py: 6 passed in 59.75s
tests/unit/test_be_mig_013_offline_sql.py: 5 passed in 6.50s
tests/unit/database/test_agentic_alembic_chain_complete.py: 5 passed in 2.30s
alembic heads: 20260924_merge_adr029_tenant_llm_heads (head)  -- exact 1
```

Roundtrip door kolomdrift heen (handmatig, op dezelfde wegwerp-database):

```
alembic downgrade 20260915_rls_rest   -> OK (edu_alignment + kolomdrift terug)
alembic upgrade head                  -> OK
alembic current                       -> 20260924_merge_adr029_tenant_llm_heads (head) (mergepoint)
educational_access: alleen code_hash; study_collections: alleen educational_access_id
```

Ruff op beide bestanden: All checks passed. Mypy op het migratiebestand:
Success: no issues found. Beide bestanden ASCII-only (geverifieerd via decode).

Wegwerp-databases (`hlm_wk1_baseline`, `wk1_verse_keten_main`) zijn na de meting
gedropt.

---

## Open aannames

- Constraint-NAMEN verschillen per migratiepad (kolomdrift's
  `uq_educational_access_code_hash` / `fk_study_collections_educational_access_id`
  versus edu_alignment's `educational_access_code_hash_key` /
  `study_collections_educational_access_id_fkey`). Bewust zo gelaten: hernoemen
  zou kolomdrift's downgrade breken. `create_all`-schema's gebruiken de
  `_key`/`_fkey`-namen; de integratietests in
  tests/integration/foundation/test_migrations.py draaien op create_all en zien
  dat verschil niet. Alembic autogenerate vergelijkt unieke constraints op
  kolommen, niet op naam.
- Staging heeft (per ketenlogica) nog steeds zowel `code` als `code_hash` staan
  en edu_alignment open; deze fix maakt die pending upgrade daar weer
  uitvoerbaar. Dat is een deploy-beslissing, geen code-wijziging.

## Risico's

- Een database die edu_alignment in de OUDE positie (pre-2026-09-18) heeft
  toegepast, voert de nieuwe inhoud nooit uit (revisie-id al geregistreerd) --
  gewenst en gedocumenteerd.
- De offline gegenereerde SQL blijft het blinde rename-script; uitvoeren van
  offline SQL op een post-kolomdrift database faalt. Dat gold ook voor de fix en
  de offline test pinde die vorm al; online is het enige gedekte pad.

---

## QA-checks

- [x] Happy path getest (verse upgrade head op echte Postgres)
- [x] Foutpad getest (niet-lege tabel -> harde fout; ongewijzigd gedrag)
- [x] Tenant-isolatie getest (RLS/policies ongemoeid; FORCE RLS volgt in 20260915)
- [x] Edge cases getest (beide kolommen aanwezig; al-aligned; roundtrips)
- [x] Data-integriteit en transacties getest (transactionele DDL, count-checks)
- [ ] Review door reviewer-prompt: volgt in Gate 2

## Definition of Done

- [x] Feature is gebouwd
- [x] Acceptatiecriteria zijn testbaar en gemeten
- [x] Open aannames zijn benoemd
- [ ] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS (Gate 2)
