# BE-DB-048 -- De migratieketen bouwt het volledige schema weer

| | |
|---|---|
| ID | BE-DB-048 |
| Sprint | SP-DB-BASELINE-001 |
| ADR | ADR-005 (tenant_id NOT NULL + RLS), ADR-036 (OP-140, OP-147 t/m OP-150) |
| Branch | `fix/db-baseline` (vertakt van `fix/council-gate`) |
| Commits | `201520ca` (baseline + oorzaak), `1d616952` (Gate 2-ronde 1) |
| Datum | 2026-08-17 |

---

## 1. Het probleem in een zin

Een verse database uit `alembic upgrade head` kwam op 120 tabellen terwijl de applicatie er
186 verwacht -- er kon dus **geen nieuwe omgeving uit de migraties worden gebouwd**.

## 2. Waarom dat gevaarlijk was zonder dat iemand het merkte

De applicatie draaide prima. Bestaande databases waren ooit met `Base.metadata.create_all`
opgebouwd en hadden alles. Elke testboom bouwt zijn schema op dezelfde manier, dus lokaal en in
CI was er niets te zien. Alleen staging en productie draaien de migraties -- en een nieuwe
klantomgeving, een tweede regio of herstel na een calamiteit zou stranden op ontbrekende
tabellen, waaronder `notifications`, `token_blacklist` (inloggen), `workflow_executions`,
`deletion_audit` (AVG-verwijderingen) en `role_permissions`.

## 3. De oorzaak lag een laag dieper (OP-147)

Er bestaan **twee** modelregistraties, en `src/alembic/env.py` gebruikte de kleinste:

| Registratie | Tabellen in `Base.metadata` |
|---|---|
| `register_all_models()` -- wat Alembic gebruikte | 143 |
| `src.core.database.import_all_models` | 186 |

Verschil: 43, **zonder importfouten** -- die modules stonden simpelweg niet in de registry.
Alles in dat verschil is voor `--autogenerate` permanent onzichtbaar: het model bestaat, de
tabel wordt nooit voorgesteld, er komt nooit een migratie. Zo zijn die 71 tabellen ontstaan.

Dezelfde blinde vlek werkt de andere kant op: een model dat de registratie mist maar in de
database wél bestaat, ziet autogenerate als **overbodig**. Precies zo verdween
`tenants.prana_budget` in `archive/a10bd0ad9807` -- de kolom die SP-COUNCIL-GATE-001 een dag
eerder moest herstellen.

Vier modellen stonden in geen van beide registraties, waarvan drie uit BE-AGT-046 van twee
dagen eerder. Daar was het symptoom omzeild met een module-level import in de test, met een
uitleg erbij, in plaats van de oorzaak te zoeken.

## 4. Wat er is gebouwd

| Onderdeel | Bestand |
|---|---|
| Alembic gebruikt de volledige registratie | `src/alembic/env.py` |
| Vier ontbrekende modules geregistreerd | `src/core/database/import_all_models.py` |
| Baseline: 71 tabellen, idempotent, uitsluitend toevoegend | `src/alembic/versions/20260817_baseline_ontbrekende_tabellen.py` |
| RLS-policies voor 69 tenant-tabellen | `src/alembic/versions/20260817_rls_baseline_tabellen.py` |
| Cross-tenant unieke index gerepareerd | `src/core/scheduling/smart/models.py` |
| Guard: elk model in de registratie | `tests/architecture/test_every_model_is_registered.py` |
| Guard: de keten bouwt het volledige schema | `tests/integration/database/test_the_chain_builds_the_whole_schema.py` |

## 5. Drie eigenschappen die er los van elkaar toe doen

**Uitsluitend toevoegend.** De generator stelde daarnaast 73 destructieve operaties voor,
waaronder `users.first_name`, `users.last_name`, `roles.permissions` en `tenants.config`. Die
zijn bewust weggelaten: dat is dataverlies en een productbeslissing (OP-150).

**De vorm convergeert vóór de indexen.** `CREATE TABLE IF NOT EXISTS` slaat een bestaande tabel
over, maar `CREATE INDEX ... ON tabel (kolom)` is alleen voorwaardelijk op de indexnaam. Een
bestaande tabel met een kolom minder liet de migratie **afbreken** -- gereproduceerd op de
testdatabase van dit project zelf, waar `email_campaigns` de kolom `status` mist. Er staat nu
per kolom een `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` tussen tabel en indexen.

**De downgrade is een echte inverse.** De eerste versie dropte onvoorwaardelijk alle 71
tabellen, ook op een database waar de upgrade ze niet had aangemaakt. Daar was `alembic
downgrade -1` een `DROP` van 71 tabellen mét data. De upgrade noteert nu vooraf welke tabellen
nog niet bestonden; de downgrade ruimt uitsluitend die op.

Bewust géén `sa.inspect(op.get_bind())`: dat crasht offline, en juist die uitweg heeft OP-148
veroorzaakt. Alle voorwaardelijkheid zit in SQL die offline gewoon meeschrijft.

## 6. Bewijs

Alles tegen echte PostgreSQL, niet beredeneerd:

| Wat | Uitkomst |
|---|---|
| Verse database, `upgrade head` | 120 -> 192 tabellen, 138 RLS-policies |
| Heen-terug-heen | 192 -> 120 -> 192, policies 138 -> 69 -> 138 |
| Bestaande tabel met een kolom minder | migratie loopt door, rij behouden, kolom toegevoegd |
| Downgrade op een bestaande database | vooraf bestaande tabel overleeft mét rij; alleen wat de migratie maakte verdwijnt |
| Offline dry-run | rc=0 |
| `alembic heads` | 1 |
| `pyright` / `mypy` / `ruff` | 0 / 0 / schoon |

## 7. Wat NIET is opgelost

| OP | Wat | Borging |
|---|---|---|
| OP-148 | 37 van de 101 migraties slaan hun werk over in offline-modus; `pre-deploy-check.sh` valideert daardoor een onvolledig schema | de guard meet nu op een echte database |
| OP-149 | Vier tabellen in de keten hebben geen ORM-model | gedateerde uitzondering + staleness-test |
| OP-150 | Kolom- en indexdrift de andere kant op; `alembic check` kan daardoor nog geen CI-poort worden | de tabellen-kant is wel geborgd |
| OP-139 | Het prana-budget kan nog niet worden bijgevuld | eigen dag; dit was het splitspunt uit de dagbrief |

## Trainingssamenvatting

- Actor: ontwikkelaar of beheerder die een nieuwe omgeving opzet
- Voorwaarde: een lege PostgreSQL-database en de repository op de huidige `develop`
- Actie: `alembic -c src/alembic.ini upgrade head`
- Systeemreactie: de keten bouwt het volledige schema -- 191 tabellen plus de boekhoudtabel van
  de baseline -- en zet Row Level Security op de tenant-gescheiden tabellen
- Succes: de applicatie start op deze database zonder ontbrekende tabellen
- Fout: draait de migratie op een database die enkele tabellen al heeft, dan worden alleen de
  ontbrekende aangemaakt en ontbrekende kolommen toegevoegd; bestaande data blijft ongemoeid
- Uitzonderingen: elke migratie van deze dag draait uitsluitend terug wat haar EIGEN upgrade
  heeft gewijzigd -- bijgehouden in een boekhoudtabel per migratie. Op een database die de tabellen al had, blijft alles staan. Kolom- en
  indexdrift wordt NIET rechtgezet -- dat is OP-150 en vraagt een aparte beslissing
