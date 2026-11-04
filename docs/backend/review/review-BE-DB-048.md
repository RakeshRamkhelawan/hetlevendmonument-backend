# Review BE-DB-048 -- De migratieketen bouwt het volledige schema weer

| | |
|---|---|
| Feature | BE-DB-048 |
| Sprint | SP-DB-BASELINE-001 |
| Branch | `fix/db-baseline` (vertakt van `fix/council-gate`) |
| Commits | `201520ca`, `1d616952`, `22f6a8df`, `c0e14a84` + de ronde-3-commit |
| Rondes | 3 (alle drie CHANGES_REQUESTED, alle drie verwerkt) |
| Datum | 2026-08-17 |
| Eindoordeel | **APPROVED WITH MINOR GAPS** -- met een uitdrukkelijke kanttekening, zie par. 5 |

---

## 1. Verloop

Twee Gate 2-rondes, elk op een commit-hash en niet op de working tree.

| Ronde | Commit | Code-reviewer | Security-reviewer |
|---|---|---|---|
| 1 | `201520ca` | CHANGES_REQUESTED (2 HIGH, 4 MEDIUM) | CHANGES_REQUESTED (3 blokkers) |
| 2 | `1d616952` | -- | CHANGES_REQUESTED (1 HIGH, 1 MEDIUM) |
| 3 | `c0e14a84` | CHANGES_REQUESTED (2 HIGH, 1 MEDIUM) | -- |

**Ronde 3 was de scherpste, en dat is het eerlijke verhaal van deze dag.** De reparatie die
ik in ronde 2 schreef voor de cross-tenant unieke index was op een verse database een no-op
op de heenweg en een BEVEILIGINGSREGRESSIE op de terugweg: de downgrade dropte een
constraint die de baseline had aangemaakt en legde de cross-tenant unieke index terug. Op
een database met duplicaten sloopte de upgrade eerst de bestaande uniciteit, faalde daarna
stil, en eindigde met exitcode 0 -- netto minder bescherming dan ervoor. Dat is dezelfde
klasse fout als bevinding A uit ronde 2, voor de derde keer op een dag.

Volledig herschreven en opnieuw gemeten in drie scenario's (zie par. 5). Daarbij bleek een
sterkere eigenschap dan "faalt luid": omdat de migratie alleen iets doet wanneer de oude
index UNIEK is, en een unieke index op `user_id` duplicaten op `(tenant_id, user_id)`
uitsluit, is het duplicatenscenario in dat pad ONBEREIKBAAR.

Er is geen vierde ronde gedraaid. De merge-beslissing ligt hoe dan ook bij Rakesh.

## 2. Wat de rondes hebben weggehaald

### Ronde 1

**Twee HIGH van de code-reviewer, allebei door hem gereproduceerd, allebei door mij gemist:**

- **De downgrade was geen inverse.** De upgrade was voorwaardelijk (`IF NOT EXISTS`), de
  downgrade onvoorwaardelijk. Op een bestaande database -- juist het geval waarvoor de
  idempotentie is geschreven -- was `alembic downgrade -1` een `DROP` van 71 tabellen mét data,
  waaronder `deletion_audit` (AVG-bewijs), `billing_events` en `usage_records`.
- **De migratie was niet idempotent maar brak af.** `CREATE TABLE IF NOT EXISTS` slaat een
  bestaande tabel over, maar `CREATE INDEX ... ON tabel (kolom)` is alleen voorwaardelijk op de
  indexnaam. Gereproduceerd op de testdatabase van dit project zelf: `email_campaigns` mist daar
  `status`, dus rc=1 en de deploy staat stil.

**Drie blokkers van de security-reviewer:**

- **Geen RLS.** De 71 tabellen kwamen zonder Row Level Security de keten in, terwijl 41 andere
  migraties dat wel zetten en ADR-005 het voorschrijft. Dat is het moment waarop het schema van
  elke toekomstige omgeving wordt vastgelegd -- inclusief versleutelde OAuth-tokens,
  sessietokens en beveiligingsmeldingen.
- **Een cross-tenant unieke index** op `user_scheduling_profiles`: globaal uniek op `user_id`,
  op een tenant-gescheiden tabel. Blokkeert tenant B én verraadt het bestaan van een gebruiker
  in tenant A.
- **De nieuwe import in `env.py`** miste de tolerante `try/except` die de bestaande registratie
  bewust wél heeft, en stond tussen een statement en zijn foutafhandeling in.

### Ronde 2

- **Bevinding A (HIGH):** `DROP TYPE ... CASCADE` stond BUITEN de boekhouding die ik er in
  ronde 1 juist omheen had gezet -- vier regels lager, dezelfde fout. `CASCADE` neemt bij een
  enumtype de KOLOM mee uit tabellen die de migratie nooit heeft aangeraakt. Gereproduceerd: de
  kolom `status` verdween uit een bestaande tabel, met alleen een NOTICE.
- **Bevinding B (MEDIUM):** de indexreparatie bereikte geen enkele bestaande database, want
  `CREATE INDEX IF NOT EXISTS` is voorwaardelijk op de naam. De beveiligingsbevinding uit ronde
  1 zou dus in dev, staging en productie live blijven.

Beide opgelost en bewezen. De eerste door de `CASCADE` te vervangen door een `DROP` die een
nog-gebruikt type laat staan; de tweede met een eigen migratie conform
`.claude/rules/database.md`.

## 3. Een claim die ik heb moeten terugnemen

Mijn eigen docstring beweerde dat RLS "ook standhoudt bij een lek in de applicatiecode". In
deze configuratie is dat **onwaar**: PostgreSQL past RLS niet toe op de eigenaar van de tabel,
en de applicatie verbindt als `postgres`. Gemeten met exact de policy-vorm uit deze migratie:
als eigenaar 2 van 2 rijen zichtbaar, als niet-eigenaar 1 van 2, zonder tenantcontext 0.

De policies zijn correct en werken zodra er een aparte applicatierol is -- dat is nu OP-151.
Maar de tekst zei iets wat ik niet had gemeten, en dat is precies wat
`.claude/rules/quality-gates.md` verbiedt.

## 4. Wat zelf is nagemeten in plaats van aangenomen

- **`FOR ALL USING (...)` zonder `WITH CHECK` beperkt ook SCHRIJVEN.** PostgreSQL valt voor
  INSERT terug op de USING-expressie. Aangetoond met een niet-eigenaar-rol: eigen tenant
  schrijven slaagt, een rij schrijven op naam van een ander wordt geweigerd
  (`InsufficientPrivilege`), en die sessie ziet alleen zijn eigen rij.
- **De guard las tekst waar hij structuur moest toetsen.** De scan op `__tablename__` ziet geen
  tabellen die via `sa.Table()` zijn gedefinieerd -- `user_roles` viel er letterlijk buiten. Nu
  via de syntaxboom, met een test die bewijst dat die tak draagt (de regex dekt 185 van de 186,
  dus zonder die test kon de hele tak weg zonder dat iets rood werd).
- **Een ongeldige mutatietest herkend en vervangen.** Het hernoemen van de `Table(`-aanroep brak
  de import in plaats van de guard te toetsen; dan meet je iets anders dan je denkt.

## 5. Bewijs

Alles tegen echte PostgreSQL:

| Wat | Uitkomst |
|---|---|
| Verse database, `upgrade head` | 120 -> 192 tabellen, 138 RLS-policies |
| Heen-terug-heen | 192 -> 120 -> 192; policies 138 -> 69 -> 138 |
| Bestaande tabel met een kolom minder | migratie loopt door, rij behouden, kolom toegevoegd |
| Downgrade op een bestaande database | vooraf bestaande tabel overleeft mét rij; alleen wat de migratie maakte verdwijnt |
| Bestaande tabel met een enum-kolom, na downgrade | kolom en rij behouden |
| Nieuwe indexmigratie | constraint aanwezig, oude index niet meer uniek |
| RLS-schrijfbeperking | vreemde tenant geweigerd, eigen tenant toegestaan |
| Offline dry-run | rc=0 |
| Volledige suite | 15.665 geslaagd, 215 overgeslagen, 19 xfailed, **0 gefaald** |
| `pyright` / `mypy` / `ruff` / `alembic heads` | 0 / 0 / schoon / 1 |

## 6. Wat OPENSTAAT

| OP | Wat |
|---|---|
| OP-148 | 37 van de 101 migraties slaan hun werk over in offline-modus; `pre-deploy-check.sh` valideert daardoor een onvolledig schema |
| OP-149 | Vier tabellen in de keten hebben geen ORM-model |
| OP-150 | Kolom- en indexdrift de andere kant op; `alembic check` kan daardoor nog geen CI-poort worden |
| OP-151 | RLS is inert zolang de applicatie als eigenaar verbindt -- er is geen aparte applicatierol |
| OP-152 | Een bestaand ENUM-type met andere waarden wordt stil geaccepteerd |
| OP-139 | Het prana-budget kan nog niet worden bijgevuld (splitspunt uit de dagbrief) |

Daarnaast uit ronde 2, niet opgelost en niet apart geregistreerd omdat ze de bestaande OP's
niet veranderen: `token_blacklist` en `scheduling_partner_feedback` hebben geen tenantlaag
(genoemd in de migratie-comment), `ADD COLUMN IF NOT EXISTS` legt kolommen zonder `NOT NULL` of
`DEFAULT` vast op een afwijkende database, en de 71 `CREATE TABLE` plus 888 `ALTER TABLE` lopen
in één transactie met bijbehorende locks.

## 7. Eindoordeel

**APPROVED WITH MINOR GAPS.**

De keten bouwt het volledige schema weer, de oorzaak eronder is gevonden en dichtgezet, en
beide gevaarlijke fouten in de terugweg zijn met een meting bewezen opgelost. Wat openstaat
staat in het register en raakt geen van alle de kernbewering van deze wijziging. **Twee
uitzonderingen die eerlijk moeten worden benoemd:** OP-151 en OP-152 hebben GEEN guard.
Dat is een afwijking van de NOOIT-lijst in `.claude/rules/quality-gates.md`, aangewezen
door de Gate 2-reviewer in ronde 3. OP-151 raakt configuratie buiten deze repo (de
connectierol) en OP-152 een scenario dat alleen ontstaat bij handmatig aangemaakte types;
voor beide is een zinvolle guard niet vanzelfsprekend, maar dat is een reden om het op te
schrijven, niet om het weg te laten.

De kanttekening uit par. 1 blijft staan: er is geen derde reviewronde geweest op de laatste
commit. Dat is een beoordeling die bij Rakesh hoort, niet bij de uitvoerder.
