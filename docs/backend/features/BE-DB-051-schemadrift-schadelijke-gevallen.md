# BE-DB-051 -- schrijven slaagt weer: de schadelijke schemadrift-gevallen

| | |
|---|---|
| **ID** | BE-DB-051 |
| **ADR** | ADR-036 Fase D / OP-150 (schemadrift model tegen keten) |
| **Sprint** | schemadrift-schadelijk-repareren, pilot december |
| **Branch** | `iter/schemadrift` |
| **Commits** | `0841e701` (meting en ratel), `8c5acd64` (reparatie) |
| **Datum** | 2026-10-24 |

---

## 1. Het probleem in een zin

Op een verse database uit de migratieketen faalde een insert via de modellen op drie plekken,
terwijl elke unittest dat niet ziet omdat die zijn schema met `create_all` bouwt.

## 2. Wat er gemeten is

`alembic check` op een verse keten meldt 401 verschillen met de modellen; de indeling staat in
`docs/backend/schemadrift-indeling-2026-10-23.md`. Daarvan waren er drie schadelijk, elk met een
echte insert als bewijs op een wegwerpdatabase:

| Geval | Foutmelding bij een insert |
|---|---|
| `governance_risk_entries.likelihood/impact`: model is een native enum, de database een VARCHAR(30) | `type "risklikelihood" does not exist` |
| `tenants.slug`: database 50 tekens, model 100 | `value too long for type character varying(50)` |
| `pack_usage_aggregates.pack_id`: database UUID, de job schrijft tekst | `column "pack_id" is of type uuid but expression is of type character varying` |

Plus drie kolommen die het model niet kent en die NOT NULL zijn zonder standaardwaarde
(`educational_access.code`, `study_collections.access_code`, `pack_usage_aggregates.company_size`).

## 3. Wat er veranderd is

- **Risico-model** (`src/core/governance/risk_register.py`): tekstkolom (VARCHAR 30, lowercase
  waarden) in plaats van een native enum. Geen migratie nodig.
- **Migratie `20261023_schemadrift_schadelijk`**: alleen verruimend. `tenants.slug` naar
  VARCHAR(100) en NOT NULL laten vallen op de drie onbekende kolommen. `downgrade()` weigert met een
  duidelijke melding als een slug langer is dan 50 tekens of een van die kolommen een lege waarde
  heeft, en laat de data dan ongemoeid.
- **`pack_usage_aggregates` uitgeschakeld tot een catalogustabel met vaste id's bestaat;
  ontwerpkeuze, eventueel met migratie, later; niet nodig voor de pilot.** Reden: de pakketsleutel
  die de aggregatiejob kent (`pack_activation_audit_logs.pack_id`, tekst) heeft geen vaste UUID.
  `domain_packs` is per klant, en de aggregaten lopen bewust over klanten heen (k-anonimiteit).
  De job (`src/core/jobs/analytics_aggregation.py`) schrijft daarom niets meer (schakelaar
  `SCHRIJF_PACK_USAGE_AGGREGATEN = False`), meldt de reden een keer op INFO en crasht niet. Het schema
  is ongewijzigd: `pack_id` (UUID tegen tekst) blijft als bekende drift in de ratel staan. Gevolg:
  `/analytics/benchmarks` blijft leeg tot die catalogus er is.
- **Correctie op de eerste indeling:** `educational_access` heeft geen extra UNIQUE-index nodig;
  `code_hash` is al globaal uniek, dus (tenant_id, code_hash) is afgedwongen.
- **Ratel** (`tests/integration/database/test_schemadrift_stijgt_niet.py`): `modify_type` van 14 naar 11.

## 4. Bewijs

| Wat | Hoe gezien |
|---|---|
| de drie schadelijke gevallen slaan nu wel | `tests/integration/database/test_schemadrift_schadelijke_gevallen.py`, 9 groen op een verse keten, vooraf 7 van 8 rood |
| downgrade weigert zonder data te raken, en downgrade plus upgrade slagen | dezelfde tests |
| de opruimstap van de job draait op het ketenschema | `test_cleanup_old_aggregations_slaagt_op_het_ketenschema` |
| de job probeert geen insert en crasht niet | `tests/unit/jobs/test_analytics_aggregation_schrijft_niets_zonder_catalogus.py`, 4 groen; met de schakelaar aan 3 rood en de schakelaartest groen |
| ratel zonder stijging | 10 groen |

## 5. Wat niet gemeten is

- Het aantal rijen in `governance_risk_entries` en `pack_usage_aggregates` op staging en productie.
  Bestaan er rijen in `governance_risk_entries` met enum-NAMEN ('RARE'), dan geeft het lijst-endpoint
  een 500; meet voor de uitrol `SELECT count(*) FROM governance_risk_entries`.
- Of een externe planner de aggregatiejob op naam aanroept.
- Of de ontwerpkeuze voor de catalogustabel (vaste UUID per pakketsleutel) nodig is voor iets anders
  dan analytics.

## Trainingssamenvatting

**Actor:** een beheerder die een nieuwe klant aanmaakt, of een medewerker die een risico-regel
vastlegt; achter de schermen de applicatie die op een database uit de migraties draait.

**Voorwaarde:** een omgeving waarvan het schema uit de migratieketen komt (staging, productie,
een nieuwe klantomgeving).

**Actie:** een klant aanmaken met een lange naam (slug van meer dan 50 tekens), of een
risico-regel opslaan.

**Systeemreactie:** de slug tot 100 tekens wordt opgeslagen; de risico-regel wordt opgeslagen en
weer teruggelezen.

**Succes:** beide handelingen slagen op de ketendatabase, niet alleen in de tests.

**Fout:** een downgrade van de migratie met data die niet past (een slug langer dan 50 tekens,
een lege waarde in een kolom die weer NOT NULL moet worden) weigert met een duidelijke melding.

**Uitzonderingen:** de dagelijkse pakketgebruiks-aggregatie schrijft niets (uitgeschakeld tot een
catalogustabel met vaste id's bestaat); het benchmark-scherm blijft daardoor leeg.

