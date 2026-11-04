# Backend Feature Specification

## Metadata

- Feature ID: BE-MIG-013
- Feature naam: Alembic migratie 20260909_adr029_edu_alignment
- Status: CHANGES_REQUESTED -> fixes doorgevoerd, herreview aangevraagd
- Auteur: Fixer_Migratie (sprint sub-agent)
- Reviewer: review-BE-MIG-013.md (CHANGES_REQUESTED; alle 6 issues opgelost)
- Datum: 2026-09-09
- Gerelateerde user story / ticket: ADR-029 Foundation Portal v1 -- migratie/model-alignment fix
- Gerelateerde router / module: `src/alembic/versions/20260909_adr029_edu_alignment.py`, `src/core/models/foundation_content.py`
- Gerelateerde frontend endpoints: Geen
- Gerelateerde database tabellen: `educational_access`, `study_collections`, `newsletter_subscriptions` (enum `newsletter_status_enum`)
- Versie: 1.1 (review-fixes: keten, defensieve cast, rowcount-checks, offline-safe, downgrade-doc, test-dekking, telling/registry)

---

## Doel en scope

### Doel

Drie gemeten afwijkingen tussen migratie `20260824_adr029_portal_v1` en de
SQLAlchemy-modellen in `src/core/models/foundation_content.py` herstellen,
zodat ORM-inserts op de educatieve tabellen werken en de enum-serialisatie
van het model matcht met de database.

### In scope

- Migratie `20260909_adr029_edu_alignment` (nieuw): herstel van
  `educational_access` (`code` String(20) -> `code_hash` String(64)),
  `study_collections` (`access_code` String(20) -> `educational_access_id`
  FK + juiste indexen) en verwijdering van de dode dubbele enum-waarde
  `bounced` uit `newsletter_status_enum` via type-recreatie.
- Modelwijziging `foundation_content.py`: `values_callable=lambda e:
  [m.value for m in e]` op de `PGEnum`s van `PortalUser.role`
  (`portal_role_enum`) en `EducationalAccess.role`
  (`educational_role_enum`).
- Uitbreiding van `tests/integration/foundation/test_migrations.py` met
  structurele dekking voor de drie problemen (10 nieuwe tests), plus
  offline-SQL-dekking van het migratiepad in
  `tests/unit/test_be_mig_013_offline_sql.py` (5 nieuwe tests).

### Out of scope

- Wijziging aan migratie `20260824_adr029_portal_v1` zelf (al in de keten;
  fixes gaan via een nieuwe migratie).
- Wijziging aan het `NewsletterStatus`-model-PGEnum (dat type bevat bewust
  de member-namen in hoofdletters; het model serialiseert namen en matcht
  daarmee de bestaande waarden).
- Herstel van verwijderde rest-data (onmogelijk: nooit bruikbaar geweest).

---

## Build summary

- **Nieuw gebouwd:** `src/alembic/versions/20260909_adr029_edu_alignment.py`, `tests/unit/test_be_mig_013_offline_sql.py` (5 tests)
- **Gewijzigd:** `src/core/models/foundation_content.py` (twee PGEnum's met values_callable + comment), `tests/integration/foundation/test_migrations.py` (10 nieuwe tests + module-docstring bijgewerkt; geen bestaande tests aangepast)
- **Verwijderd:** Geen
- **Beinvloede bestaande flows:** ORM-inserts op `EducationalAccess`, `StudyCollection`, `PortalUser` (rol-persistatie); geen API-flows geraakt.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-MIG-013 | Alembic migratie 20260909_adr029_edu_alignment | Alembic migration | `src/alembic/versions/20260909_adr029_edu_alignment.py` | Nieuw | ADR-029 educatieve tabellen alignment |
| BE-MDL-016 | values_callable op PortalRole/EducationalRole PGEnum | SQLAlchemy model-wijziging | `src/core/models/foundation_content.py` (`PortalUser.role`, `EducationalAccess.role`) | Wijziging | Enum-serialisatie ORM -> DB |

---

## API-flows

N.v.t. -- Alembic migratie en model-definitie; geen endpoints.

---

## Detaildocumentatie per artefact

---

## [BE-MIG-013] Alembic migratie 20260909_adr029_edu_alignment

### 1. Type

Alembic migration (revision `20260909_adr029_edu_alignment`, down_revision
`20260716_backfill_prana_budgets` -- werkelijke head; `20260715` en
`20260716` hangen onder `20260824`. Volgorde in de keten:
`20260824 -> 20260715 -> 20260716 -> 20260909`; `alembic heads` rapporteert
exact een head. Eerdere claim dat `20260824` zelf head was, was onjuist en
is met deze down_revision gecorrigeerd.)

### 2. Locatie

- Bestandspad: `src/alembic/versions/20260909_adr029_edu_alignment.py`

### 3. Gerelateerde flow

ADR-029 educatieve tabellen alignment.

### 4. Doel

De door migratie `20260824_adr029_portal_v1` gemaakte afwijkende kolommen
en enums recht trekken naar de ORM-modellen, zodat elke ORM-insert slaagt.

### 5. Functionele beschrijving

De upgrade doet vier dingen, in vaste volgorde:

1. Verwijdert de dode dubbele enum-waarde `bounced` (lowercase) uit
   `newsletter_status_enum`. PostgreSQL kan enum-waarden niet droppen
   zonder type-recreatie; de migratie maakt het type daarom expliciet
   opnieuw aan (RENAME naar `_old`, CREATE TYPE zonder `bounced`, ALTER
   COLUMN ... USING-cast op `newsletter_subscriptions.status`, DROP TYPE
   `_old`). Alleen als `bounced` daadwerkelijk bestaat (buiten offline
   mode geverifieerd tegen `pg_enum`; offline mode genereert blind).
   De USING-cast is defensief: rijen met de dode lowercase `bounced`
   mappen naar `BOUNCED`, anders zou de cast op zulke rijen falen en de
   hele migratie terugrollen.
2. Verwijdert alle rijen uit `study_collections` en `educational_access`.
   Reden: de ORM kon nooit met deze tabellen schrijven (afwijkende
   kolommen), dus elke bestaande rij is een onbruikbaar plaintext-restant
   (ongehaste toegangscodes). Dit is de veiligste route voor de NOT NULL /
   FK-wijzigingen en staat expliciet in de docstring. Na elke DELETE is
   een rowcount-verificatie: blijven er rijen staan (mogelijk onder RLS
   als niet-eigenaar), dan faalt de migratie hard. EIGENAAR-VEREISTE:
   draai als tabel-eigenaar of een rol die RLS bypass't.
3. Herstelt `educational_access`: dropped de unieke constraint op `code`
   (eerst blind `DROP CONSTRAINT IF EXISTS educational_access_code_key`,
   daarna in online mode defensief opgezocht in `pg_constraint` voor een
   afwijkende naam), dropped index `idx_ea_tenant_code`, hernoemt `code`
   naar `code_hash` met type varchar(64), maakt unieke constraint
   `educational_access_code_hash_key` en recreate index
   `idx_ea_tenant_code` op `(tenant_id, code_hash)` uniek -- exact volgens
   het model.
4. Herstelt `study_collections`: dropped indexen `idx_sc_tenant_code` en
   `ix_study_collections_access_code`, dropped kolom `access_code`, voegt
   `educational_access_id` Integer NOT NULL toe met FK
   `study_collections_educational_access_id_fkey` naar
   `educational_access.id` ON DELETE CASCADE, plus index
   `ix_study_collections_educational_access_id` en recreate composite
   index `idx_sc_tenant_code` op `(tenant_id, educational_access_id)` --
   exact volgens het model.

De downgrade draait alle structuurwijzigingen terug (kolommen, indexen,
constraints, enum-waarde `bounced`), kan de in stap 2 verwijderde rijen
niet herstellen en is alleen uitvoerbaar op lege tabellen (anders eerst
`TRUNCATE study_collections, educational_access;` -- zie downgrade-docstring
voor de reden).

### 6. Technische beschrijving

Stijl conform bestaande migraties: `_is_postgresql()` helper, raw SQL via
`op.execute(sa.text(...))` alleen achter de dialect-guard. Alle DDL staat
in een transactie (Alembic per-migration transaction); de enum-recreatie is
in Postgres transaction-safe omdat het RENAME/CREATE/ALTER/DROP-type patroon
geen `ALTER TYPE ... ADD VALUE` gebruikt. De migratie is ook offline-safe
(`alembic upgrade <a>:<b> --sql`): data-afhankelijke checks slaan over op
een `None`-resultaat en de DDL is blind correct.

### 7. Zichtbaarheids- en toegangsregels

N.v.t. -- database-migratie, geen runtime-toegang.

### 8. Request-specificatie

N.v.t.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- `code_hash`: varchar(64) NOT NULL, uniek (`educational_access_code_hash_key`).
- `educational_access_id`: integer NOT NULL, FK naar `educational_access.id`
  ON DELETE CASCADE.
- Unieke index `idx_ea_tenant_code` op `(tenant_id, code_hash)`.
- Composite index `idx_sc_tenant_code` op `(tenant_id, educational_access_id)`.
- `newsletter_status_enum` bevat exact `PENDING_OPT_IN`, `SUBSCRIBED`,
  `UNSUBSCRIBED`, `BOUNCED`.

### 11. Business rules

- Toegangscodes worden nooit als plaintext opgeslagen; het model eist
  SHA-256 hashes (`code_hash` String(64)).
- Een study collection hangt altijd aan precies een educational access
  code (NOT NULL FK); mee-verwijderd bij CASCADE.

### 12. Afhankelijkheden

- down_revision `20260716_backfill_prana_budgets` (werkelijke head van de
  tak; `20260824_adr029_portal_v1` maakt de tabellen/enums aan, daaronder
  hangen `20260715` en `20260716`).
- Model `EducationalAccess` / `StudyCollection` in
  `src/core/models/foundation_content.py`.

### 13. Foutafhandeling

- Niet-Postgres dialecten: enum-recreatie en constraint-lookup worden
  overgeslagen (guard), overige DDL is dialect-neutraal.
- Upgrade faalt hard als de verwachte indexen/kolommen ontbreken
  (gewenst: migraties moeten luid falen, niet stil corrupt zijn).
- RLS/eigenaar: draait de migratie als niet-eigenaar met RLS, dan kunnen
  de DELETE's in stap 2 stille no-ops zijn; de rowcount-verificatie faalt
  dan hard met een duidelijke melding ("migratie moet als tabel-eigenaar
  draaien").
- Offline mode (`alembic upgrade <a>:<b> --sql`): alle data-afhankelijke
  checks (pg_enum-lookup, rowcount, pg_constraint-lookup) worden overgeslagen
  en de DDL blind gegenereerd; het recreatiepad is defensief genoeg
  (IF EXISTS + CASE-cast) om ook blind correct te zijn.

### 14. Transacties en data-integriteit

Een migratie = een transactie (Alembic). Verwijderde rest-data is
onomkeerbaar; downgrade herstelt alleen structuur. De DELETEs in stap 2
staan voor alle NOT NULL/FK-wijzigingen zodat die gegarandeerd slagen.

### 15. Telemetry / logging / tracing

N.v.t.

### 16. Caching

N.v.t.

### 17. Acceptatiecriteria

- [ ] Migratie draait zonder fouten op een database waar `20260824_adr029_portal_v1` op gedraaid heeft
- [ ] `educational_access` heeft kolom `code_hash` varchar(64) NOT NULL, uniek; kolom `code` ontbreekt
- [ ] `study_collections` heeft `educational_access_id` NOT NULL met FK naar `educational_access.id`; kolom `access_code` ontbreekt
- [ ] Indexen `idx_ea_tenant_code` (unique, tenant_id + code_hash), `idx_sc_tenant_code` (tenant_id + educational_access_id), `ix_study_collections_educational_access_id` bestaan
- [ ] `newsletter_status_enum` bevat geen `bounced` meer; de 4 hoofdletter-waarden blijven
- [ ] ORM-insert van `EducationalAccess`, `StudyCollection` en `PortalUser` met een rol slaagt
- [ ] `pytest --stepwise` op de foundation-testbestanden blijft groen

### 18. Integratoruitleg

- De educatieve portal-tabellen zijn nu consistent met de modellen;
  toegangscodes worden als hash (`code_hash`) opgeslagen.
- Bestaande toegangscodes/study-collections uit de kapotte periode zijn
  verwijderd en moeten opnieuw aangemaakt worden via de API.
- Geen API-wijziging; alleen database-structuur en ORM-serialisatie.

### 19. Trainingssamenvatting

- **Actor:** Alembic (upgrade)
- **Voorwaarde:** `20260909` hangt onder `20260716_backfill_prana_budgets`
  (dus `20260824`, `20260715`, `20260716` zijn gedraaid); migratie draait
  als tabel-eigenaar (RLS-bypass)
- **Actie:** draai `20260909_adr029_edu_alignment`
- **Systeemverwerking:** dode enum-waarde verwijderd, rest-data gewist, kolommen/indexen/FK op model gelijk getrokken
- **Succesrespons:** migratie gecommit, schema matcht de ORM-modellen
- **Foutrespons:** harde migratie-fout bij ontbrekende verwachte structuur
- **Uitzonderingen:** downgrade herstelt geen verwijderde rijen

---

## [BE-MDL-016] values_callable op PortalRole/EducationalRole PGEnum

### 1. Type

SQLAlchemy model-wijziging.

### 2. Locatie

- Bestandspad: `src/core/models/foundation_content.py`
  (`PortalUser.role`, `EducationalAccess.role`)

### 4. Doel

SQLAlchemy serialiseert bij een PEP-435-enum-PGEnum zonder
`values_callable` de member-NAMEN (hoofdletters). Migratie
`20260824_adr029_portal_v1` maakte `portal_role_enum` en
`educational_role_enum` echter met de lowercase `.value`s van de
Python-enums. Elke ORM-insert/update van een rol faalde daarom met een
enum-waarde-fout. De andere PGEnum's in dit bestand blijven zonder
`values_callable`: hun DB-types bevatten bewust de member-namen
(hoofdletters), dus serialisatie op namen is daar correct.

### 17. Acceptatiecriteria

- [ ] ORM-insert met `PortalRole.ADMIN` schrijft `'admin'` naar de DB
- [ ] ORM-insert met `EducationalRole.STUDENT` schrijft `'student'`
- [ ] Bestaande enums (`ContentType`, `Privacy`, e.d.) blijven op namen serialiseren

---

## Integratorhandleiding

Zie "Integratoruitleg" bij BE-MIG-013.

---

## Open aannames

- Er is geen productiedata op `educational_access` / `study_collections`
  die waard is om te bewaren (de ORM kon er nooit mee schrijven; restanten
  zijn plaintext-codes).
- De testdatabase-fixture bouwt het schema via `Base.metadata.create_all`,
  niet via alembic; de integratie-tests dekken daarom model<->schema. Het
  migratiepad zelf wordt gedekt door de offline-SQL-test
  `tests/unit/test_be_mig_013_offline_sql.py`; een echte `upgrade head`
  tegen een gemigreerde wegwerp-database blijft gewenst in CI.
- `BE-MDL-016`-toewijzing: het agent-brief
  `2026-08-01-sprint-opstarten-adr036-fase-b.md` waarschuwt dat BE-MDL-016
  "niet meer vrij" zou zijn ("prefix op 029"). Die claim is nagekeken: de
  ID-REGISTRY (verplichte bron) toont als hoogste BE-MDL-015, er bestaat
  geen andere feature-spec die BE-MDL-016 claimt, en de "029"-vermeldingen
  in plannen zijn ADR-029-sub-ID's (`BE-MDL-029-001` e.d.). BE-MDL-016 is
  dus geverifieerd vrij en geregistreerd.

## Open vragen

- Review CHANGES_REQUESTED (review-BE-MIG-013.md): alle 6 issues zijn
  opgelost; herreview door de reviewer-prompt is nog te draaien.

## Risico's

- Data-verlies op de twee educatieve tabellen is bewust en gedocumenteerd
  (onbruikbare rest-data). Downgrade kan dat niet herstellen.
- De downgrade is alleen uitvoerbaar op lege tabellen; op een gevulde
  database moet eerst expliciet getruncate worden (anders faalt de
  downgrade hard op `access_code nullable=False` zonder default en op
  varchar(64) -> varchar(20) bij echte hashes).
- Eerdere versie van deze spec noemde een multi-head "pre-existing"; dat
  was onjuist -- zonder deze migratie was er geen multi-head. De eerste
  versie van de migratie creerde die wel; dat is gefixt met
  `down_revision = "20260716_backfill_prana_budgets"` (`alembic heads`
  rapporteert nu exact een head).

---

## QA-checks

- [x] Artefact aanwezig in codebase
- [x] Ruff groen op alle gewijzigde/nieuwe bestanden
- [x] 59/59 unit-tests `tests/unit/test_foundation_models.py` groen (incl. ORM-inserts met alle rollen)
- [x] 5/5 offline-SQL-tests `tests/unit/test_be_mig_013_offline_sql.py` groen
- [x] `alembic heads` rapporteert exact een head (`20260909_adr029_edu_alignment`)
- [x] `alembic upgrade 20260716_backfill_prana_budgets:20260909_adr029_edu_alignment --sql` genereert het volledige migratiescript incl. type-recreatie en CASE-cast
- [ ] Integratie-tests tegen echte Postgres (nog niet gedraaid: geen testdatabase beschikbaar, Docker onbeschikbaar)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten zijn geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [ ] Review door reviewer-prompt: CHANGES_REQUESTED, fixes doorgevoerd, herreview te draaien
