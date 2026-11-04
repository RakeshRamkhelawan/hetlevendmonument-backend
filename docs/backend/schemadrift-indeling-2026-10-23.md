# Schemadrift: indeling van de meldingen van `alembic check` (2026-10-23)

Gemeten op een verse database uit de migratieketen, basis `76934611`. Alleen gemeten en
ingedeeld: geen migratie, geen model, geen data gewijzigd.

## Hoe gemeten

`scripts/schemadrift_meten.py` (nieuw) draait dezelfde stappen als `alembic check` en houdt de
lijst vast. `python scripts/schemadrift_meten.py --lijst` geeft elke melding; zonder vlag het
aantal per soort. Voorwaarde: `DATABASE_URL` wijst naar een database op head.

**Totaal: 401 meldingen.** De regie meldde 392 (gevonden door sessie 60). Het verschil van 9
is niet verklaard: ik heb niet nagemeten op welke basis 60 mat. Draai het script op die basis
om het te zien.

## Indeling per soort

Oordeel: **schadelijk** = de applicatie kan er vandaag op falen of een regel niet afdwingen;
**zonder gevolg** = het verschil is echt maar de applicatie merkt het niet; **meetfout** = het
verschil komt door hoe alembic vergelijkt, niet door de database.

| Soort | Aantal | Voorbeelden | Oordeel |
|---|---|---|---|
| modify_comment | 106 | kolomcommentaar leeg in database, gevuld in model (84) of anders (22) | zonder gevolg |
| add_index | 114 | 77 zelfde kolommen onder andere indexnaam; 37 echt ontbrekend, waarvan 13 op `tenant_id` en 2 UNIQUE | 77 meetfout (naamverschil); 35 zonder gevolg; de 2 UNIQUE **schadelijk** |
| remove_index | 64 | 26 naamverschil; 38 index alleen in de database | zonder gevolg (extra indexen kosten alleen schrijftijd) |
| modify_nullable | 54 | 47 database losser (kolom mag leeg, model eist waarde); 7 database strenger | zonder gevolg, zie nullable-meting |
| modify_type | 14 | zie de tabel hieronder | gemengd |
| remove_column | 13 | 10 kolommen alleen in de database die leeg mogen zijn; 3 NOT NULL zonder standaardwaarde | 10 zonder gevolg; 3 **schadelijk** zodra de tabel gebruikt wordt |
| add_fk / remove_fk | 7 / 13 | 7 paren zijn alleen een naamverschil; 6 verwijzingen bestaan alleen in de database | meetfout / zonder gevolg (database strenger) |
| add_constraint / remove_constraint | 1 / 12 | o.a. `tenants.slug`: unique constraint in de database tegen unique index in het model | zonder gevolg (zelfde uniekheid, andere vorm) |
| add_table_comment / remove_table_comment | 2 / 1 | tabelcommentaar | zonder gevolg |

De splitsing "naamverschil" tegen "echt ontbrekend" bij de indexen en de verwijzingen komt uit
een vergelijking van de kolomverzameling per tabel tegen `pg_index`; die analyse draaide ik
als wegwerpscript buiten de repo. De aantallen 77/37 en 26/38 zijn dus niet te herleiden met
`schemadrift_meten.py` alleen.

### modify_type (14), per kolom

| Kolom | Database | Model | Oordeel |
|---|---|---|---|
| governance_risk_entries.likelihood, .impact | VARCHAR(30) | native Enum `risklikelihood` / impact-enum | **schadelijk**: bewijs 1 |
| pack_usage_aggregates.pack_id | UUID | String(100) | **schadelijk**: bewijs 2 |
| pack_usage_aggregates.date | DATE | DateTime(timezone) | hoort bij bewijs 2; apart niet gemeten |
| tenants.slug | VARCHAR(50) | String(100) | **schadelijk**: bewijs 3 |
| 7 tijdkolommen in 5 governance-tabellen | TIMESTAMP zonder tijdzone | DateTime(timezone=True) | zonder gevolg: bewijs 4 |
| roles.name | VARCHAR(100) | String(50) | zonder gevolg (database ruimer) |
| collective_knowledge.embedding | BYTEA | eigen type EmbeddingType | meetfout (alembic kent het eigen type niet) |

De zeven tijdkolommen: governance_accuracy_metrics.recorded_at, governance_alerts.created_at en
last_seen_at, governance_authority_reports.submitted_at en created_at,
governance_quality_checks.checked_at, governance_risk_entries.last_reviewed.

## Bewijs per schadelijke soort

Alle bewijzen zijn echte inserts met de modellen op de wegwerpdatabase, in een transactie die
werd teruggedraaid.

1. **governance_risk_entries.likelihood/impact.** Het model (`src/core/governance/risk_register.py:88`)
   gebruikt een native Postgres-enum; de keten maakte VARCHAR(30). Insert uit het model:
   `UndefinedObjectError: type "risklikelihood" does not exist`. Elke schrijfactie via het
   model op die tabel faalt. Of de tabel op staging of productie rijen heeft of gebruikt
   wordt, heb ik niet gemeten.
2. **pack_usage_aggregates.** De job `src/core/jobs/analytics_aggregation.py:362` maakt een
   `PackUsageAggregate` met `pack_id` als tekst. Insert met zulke waarden:
   `DatatypeMismatchError: column "pack_id" is of type uuid but expression is of type
   character varying`. Daarnaast bestaat `company_size` (NOT NULL, geen standaardwaarde)
   alleen in de database; een insert uit het model zou ook daarop stuklopen.
3. **tenants.slug.** Een slug van 60 tekens: `StringDataRightTruncationError: value too long for
   type character varying(50)`. Het model belooft 100; slugs van 51 tot 100 tekens falen dus.
4. **TIMESTAMP tegen DateTime(timezone=True) is NIET schadelijk** (ik vermoedde eerst van wel):
   een tijdzone-bewuste waarde schrijven lukt (insert in `governance_alerts` geslaagd,
   sessietijdzone UTC). Teruggelezen komt een waarde zonder tijdzone terug, en vergelijken met
   een bewuste tijd in Python geeft `TypeError` (gemeten). De enige lezer die ik nakeek,
   `src/core/governance/alert_manager.py:97`, vangt dat al af (`replace(tzinfo=timezone.utc)`).
   De andere lezers van deze kolommen heb ik niet nagelopen.
5. **educational_access.code en study_collections.access_code** (NOT NULL zonder
   standaardwaarde, niet in het model): `EducationalAccess(` en `StudyCollection(` worden
   nergens in `src/` aangemaakt. Zonder gevolg vandaag; schadelijk zodra iemand er schrijft.
6. **Twee UNIQUE-indexen die het model belooft bestaan niet.** Het model wil
   `educational_access(tenant_id, code_hash)` en
   `pack_usage_aggregates(date, sector, company_type, employee_bucket, pack_id)` uniek. De
   database heeft onder dezelfde naam een index op andere (oudere) kolommen:
   `idx_ea_tenant_code` op `(tenant_id, code)` en `idx_usage_agg_unique` op
   `(date, sector, company_size, pack_id)` (gelezen uit `pg_indexes`). De uniekheid die het
   model bedoelt wordt dus niet afgedwongen: dubbele rijen zijn mogelijk.

## Nullable-meting (waarom `modify_nullable` zonder gevolg is)

Alle 54 vergeleken met `Base.metadata` plus `information_schema`: 47 keer is de database losser
(een model-insert slaagt altijd). 7 keer is de database strenger (NOT NULL, model nullable);
bij alle 7 is er een standaardwaarde, dus een insert zonder waarde faalt niet. Een eerdere,
voorlopige indeling in deze sessie noemde 39 risicovolle gevallen; dat was onjuist (richting
omgedraaid) en is hier gecorrigeerd.

## Reparatievoorstel, in volgorde

Niets hiervan is uitgevoerd.

1. **Schadelijk, zonder DROP.** Een migratie die `governance_risk_entries.likelihood` en
   `.impact` laat aansluiten (de database naar enum, of het model naar tekst),
   `pack_usage_aggregates.pack_id` laat aansluiten (eerst meten welke waarden de job vult),
   en `tenants.slug` verbreedt naar VARCHAR(100). Migratie nodig: ja. DROP: nee. Downgrade:
   werkt voor verbreden niet zonder voorwaarde (terug naar 50 faalt bij langere slugs); die
   voorwaarde hoort in de downgrade.
2. **De 2 UNIQUE-indexen** op de kolommen van het model zetten. Eerst meten of er dubbele rijen
   zijn, anders faalt de migratie. Migratie nodig: ja.
3. **De 3 NOT NULL-kolommen zonder modelkennis** (`educational_access.code`,
   `pack_usage_aggregates.company_size`, `study_collections.access_code`): in het model
   opnemen of NOT NULL laten vallen. **Verwijderen is een DROP en onomkeerbaar voor data:
   interlock 1, wacht op Rakesh.** Mijn aanbeveling is geen DROP.
4. **De 37 ontbrekende indexen**, waaronder 13 op `tenant_id`: toevoegen is niet-destructief
   maar kan op grote tabellen een lock geven; per tabel `CREATE INDEX CONCURRENTLY` overwegen.
5. **De rest** (commentaar, naamverschillen, extra indexen en verwijzingen in de database):
   niets doen of het model laten volgen. `remove_index` en `remove_fk` zijn DROPs: alleen met
   Rakesh zijn woord.

## De ratel

`tests/integration/database/test_schemadrift_stijgt_niet.py` legt het aantal per soort vast
(de soort is de alembic-bewerking, `add_index` e.d.) en faalt als een aantal STIJGT of stil
DAALT (de baseline moet dan mee omlaag).

Gemeten: 10 tests groen in 73 s op de ongewijzigde stand. Mutatiebewijs: een kolom met index
aan `Tenant` toegevoegd zonder migratie -> `test_geen_soort_stijgt_boven_de_baseline` ROOD; het
script gaf `add_column` 0 -> 1 en `add_index` 114 -> 115. Model daarna teruggezet uit een
kopie (`git status` leeg voor dat bestand).

## Wat niet gemeten is

- Waarom 60 op 392 uitkwam en deze meting op 401.
- Of `governance_risk_entries` en `pack_usage_aggregates` op staging of productie rijen hebben
  en of de code die ze schrijft daar echt draait.
- Alle lezers van de zeven tijdkolommen (alleen `alert_manager.py` bekeken).
- Of er dubbele rijen bestaan die de twee UNIQUE-indexen zouden weigeren.
- De ratel draait lokaal op een verse keten; hij is niet in CI of in de volledige testronde
  gemeten.

## Vervolg 2026-10-24: wat er gerepareerd is (commit 8c5acd64, niets gepusht)

- **Risico-model** (`governance_risk_entries`): het model gebruikt nu een tekstkolom (VARCHAR 30,
  waarden lowercase) in plaats van een native enum. Geen migratie nodig; er stond nooit een rij in.
  Gezien: insert en terugleesactie via asyncpg slagen op een verse keten.
- **`tenants.slug`** naar VARCHAR(100) en **NOT NULL laten vallen** op `educational_access.code`,
  `study_collections.access_code`, `pack_usage_aggregates.company_size`: migratie
  `20261023_schemadrift_schadelijk`, alleen verruimend. De downgrade weigert bij een slug langer dan
  50 tekens of een lege waarde, en laat de data dan ongemoeid (gezien: 8 integratietests groen,
  inclusief downgrade-weigering en downgrade plus upgrade).
- **educational_access heeft geen extra UNIQUE nodig (correctie op de eerste indeling):**
  `code_hash` is al globaal uniek (`uq_educational_access_code_hash`), dus uniekheid op
  (tenant_id, code_hash) is al afgedwongen. De ontbrekende index in de melding is dubbelop.
- **pack_usage_aggregates uitgeschakeld tot een catalogustabel met vaste id's bestaat;
  ontwerpkeuze, eventueel met migratie, later; niet nodig voor de pilot.** Besluit regie (b),
  2026-10-23. De pakketsleutel die de job kent (`pack_activation_audit_logs.pack_id`, tekst) heeft
  geen vaste UUID: `domain_packs` is per klant, en de aggregaten lopen over klanten heen. De job
  schrijft niets meer (schakelaar `SCHRIJF_PACK_USAGE_AGGREGATEN = False`), meldt de reden een keer op
  INFO en crasht niet. Het schema is ongewijzigd, dus `pack_id` (UUID tegen tekst) en de bijbehorende
  UNIQUE-index blijven als bekende drift in de ratel staan.
- **Ratel:** `modify_type` 14 naar 11; de andere soorten ongewijzigd.

## Nieuwe bevinding (nog niet gerepareerd, eigen brief)

Het model van `educational_access` (en zeven andere enums in `src/core/models/foundation_content.py`:
content_type, privacy, content_status, tag_type, portal_role, takedown_status, newsletter_status)
schrijft enum-NAMEN (`STUDENT`) terwijl de migratie de WAARDEN (`student`) als label aanmaakte. Een
insert via het model op `educational_access` faalt gemeten met `invalid input value for enum
educational_role_enum: "STUDENT"`. Of de andere zeven enums hetzelfde doen en of die tabellen
gebruikt worden is niet gemeten; alleen `EducationalRole` is bevestigd.
