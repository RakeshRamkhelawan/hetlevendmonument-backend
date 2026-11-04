# BE-SEC-044 -- Drie defecten die niets meldden

| | |
|---|---|
| **ID** | BE-SEC-044 |
| **ADR** | ADR-036 Fase D / D1, D2, D3 |
| **Sprint** | SP-RLS-SWITCH-001, fase 0 |
| **Branch** | `fix/fase0-defecten` |
| **Commits** | `9d54ac3d`, `e3597ace`, `14db6caf` |
| **Datum** | 2026-08-17 |

---

## 1. Wat deze drie gemeen hebben

Alle drie waren actief in productie, geen van drieen gaf ooit een signaal. Ze zijn niet
gevonden door een foutmelding maar door een meting die iets anders zocht: het onderzoek
naar de rolwissel (OP-151). Dat is het patroon om te onthouden -- **er komt nooit een
melding wanneer iets NIET gebeurt.**

## 2. D1 -- ingetrokken tokens bleven geldig

### Gemeten, voor de fix

```
rij staat in de database (raw SQL)                : 1
ORM ZONDER tenantcontext (= het /api/v1/auth-pad) : None
ORM MET tenantcontext                             : <TokenBlacklist(...)>

>> _is_token_blacklisted() geeft: False   ("niet ingetrokken")
>> is_token_valid() geeft dan   : True
```

Uitloggen en tokenintrekking deden niets.

### De oorzaak zat niet in het auth-pad

`src/core/database/tenant_query_filter.py` had twee takken die dezelfde vraag
beantwoorden -- "hoort deze entiteit bij een tenant?" -- en ze deden dat verschillend:

| tak | gedrag |
|---|---|
| MET tenant | `if entity_class and hasattr(entity_class, "tenant_id")` -- tabellen zonder die kolom worden met rust gelaten |
| ZONDER tenant | `statement.where(literal(False))` -- ALLES wordt leeggemaakt |

`token_blacklist` heeft geen `tenant_id`, en `/api/v1/auth/*` is bij ontwerp van
tenantcontext uitgesloten (`tenant_middleware.py:75-82`). De INSERT bij het intrekken
slaagde (die tak filtert niet), de SELECT bij het controleren vond hem nooit.

### De fix

EEN antwoord voor beide takken. Een tabel zonder `tenant_id` bevat per definitie geen
gegevens van een andere klant; leegmaken beschermde daar niets en brak wel. De
`audit_logs`-uitzondering geldt daarmee ook niet langer maar in de helft van de gevallen.

Een entiteit die NIET kon worden herleid telt als tenant-gescheiden -- bewust fail-secure.
De geen-tenant-tak verliest dus geen enkele bescherming die hij had.

**Na de fix:** `_is_token_blacklisted()` geeft `True`, `is_token_valid()` geeft `False`.

## 3. D2 -- de queue `calendar_sync` had geen consument

`src/core/scheduling/webhooks/handlers.py:203` doet `sync_calendar_integration.send(...)`.
Het gedeployde commando is `dramatiq src.workers.workflow_worker:redis_broker
src.workers.actors` (`Dockerfile:168`, `docker-compose.yml:182`), en `src/workers/actors.py`
sloot de calendar-actors expliciet uit. Agenda-synchronisatie schreef in het niets;
`refresh_expiring_webhooks` draaide nooit, dus webhooks die binnen 24 uur verlopen werden
niet vernieuwd.

### De opgegeven reden was onwaar

De uitsluiting droeg een toelichting: `calendar_sync_worker` zou via
`src/workers/__init__.py` een import afdwingen die `DATABASE_URL` bij import vereist.
**Weerlegd door meting:** `actors.py` zit in datzelfde pakket, dus die keten liep sowieso
al. Met de omgevingsvariabelen van de container laden alle drie de modules samen zonder
fout; na de fix staan er 22 actors op de broker, waaronder beide.

**Na de fix, gemeten met het gedeployde commando:**

```
actors op de broker: 22
  refresh_expiring_webhooks  <- nu wel geladen
  sync_calendar_integration  <- nu wel geladen
```

## 4. D3 -- een bewaartermijn die niemand uitvoerde

`cleanup_agent_critiques` bestond sinds 2026-08-05 met een termijn van 180 dagen en stond
in geen enkele scheduler-job. De actor was wel op de broker geregistreerd -- hij KON
draaien, alleen plande niemand hem in.

Wat het misleidend maakte: `agent_critiques` staat WEL in `_RETENTION_ALLOWED_TABLES`. Wie
die lijst leest concludeert dat de termijn gehandhaafd wordt. Een ontbrekende regel was
minder erg geweest dan deze halve.

Ingepland op 03:05 UTC. De derde actor komt uit HETZELFDE import-statement als de andere
twee -- `test_dsm006_ar_governance_fan_out.py` telt import-STATEMENTS per modulepaar, en
een tweede zou `agent_runtime -> governance` van 7 naar 8 tillen.

## 5. Guards

| Guard | Bewaakt |
|---|---|
| `test_the_tenant_filter_only_blanks_tenant_tables.py` (nieuw) | vier tests, beide richtingen, op SQLite -- dus in de blokkerende CI-stap |
| `test_every_dispatched_actor_is_loaded_by_a_worker.py` (nieuw) | elke `.send()` heeft een consument; instappunten uit de compose-bestanden |
| `test_cleanup_actors_are_scheduled.py` (bestaand) | `KNOWN_UNSCHEDULED` is nu leeg |

De tweede guard betrapte onderweg een fout van mijzelf: ik had twee instappunten
hardgecodeerd en miste de tweede workercontainer (`docker-compose.yml:353`), wat vijf
vals-positieven opleverde. Hij leest ze nu uit compose, zodat een nieuwe workercontainer
vanzelf meetelt, en houdt een verzameling modules per actornaam bij omdat dezelfde naam in
twee bestanden kan staan.

## 6. Bewijs

```
volledige suite (-n 4)  15689 passed, 0 failed, exit 0
pyright                 0 errors
mypy-audit              0, baseline 0
ruff check src/ tests/  All checks passed
```

## 7. Wat NIET is opgelost

**Een dood modulepaar (D2b).** `src/core/workflow/api.py:22` importeert
`execute_workflow_task` uit `src.core.workflow.worker` -- een dubbele module naast
`src/workers/workflow_worker.py`, waarvan alleen de tweede wordt gedeployd. Dat leek een
tweede schrijf-in-het-niets, maar is het niet: **gemeten heeft `core/workflow/api.py` nul
importeurs buiten zichzelf**, dus die router is nergens gemount en de `.send()` op regel
308 draait nooit. Consistent met de `get_db_session()` op regel ~125 die
`NotImplementedError` gooit. Het is dode code, net als `src/core/database/postgres.py`.
Opruimen raakt twee modules en verdient een eigen wijziging; gedateerd uitgezonderd met
staleness-test.

**Een guard die ik niet werkend kreeg, in twee pogingen.** Ik wilde de retentie-allowlist
aan de daadwerkelijke uitvoering koppelen, want dat was wat D3 misleidend maakte.

*Poging 1* toetste of de tabelnaam voorkomt in een BESTAND met minstens een ingeplande
actor. `retention_cleanup.py` bevat ze allemaal, dus elke naam gold als gedekt: twee
mutaties die rood hadden moeten worden bleven groen.

*Poging 2* koppelde per FUNCTIE -- de AST van elke ingeplande actor plus wat die binnen
dezelfde module aanroept. Die stond bij de basismeting al rood op `agent_critiques`,
terwijl die actor wel degelijk is ingepland. **De oorzaak is vastgesteld en is de moeite
voor wie dit oppakt:** `_RETENTION_ALLOWED_TABLES` bevat tabelnaam-STRINGS, terwijl de
opruimactors naar ORM-KLASSEN verwijzen (`AgentCritique`, niet `"agent_critiques"`). Een
string-vergelijking kan die twee niet overbruggen; er is een afbeelding van model naar
`__tablename__` voor nodig. Bijkomend: doordat de basis al rood stond, bewees mutatie 1
niets -- een rode test die roder wordt is geen bewijs.

*Poging 3* legde de ontbrekende brug wel -- klassenaam -> `__tablename__` uit de
modeldefinities -- en de basismeting was groen. Maar de mutaties "haal een opruimjob uit
de scheduler" bleven allebei groen. Oorzaak: `_ingeplande_namen()` telde ook
`ast.ImportFrom`, en de drie actors worden in `_governance_cleanup_actors()` samen
geimporteerd. Die import blijft staan als je de `add_job` weghaalt, dus elke actor gold
als ingepland.

**Wat de volgende poging moet doen, met de drie diagnoses als richting:** tel als
"ingepland" uitsluitend de callables die als eerste argument aan `add_job(...)` worden
meegegeven (`self._run_cleanup_agent_critiques`), volg die methode naar de `.send()` die
hij doet, en pas dan naar de actor in `retention_cleanup.py`. Imports en losse aanroepen
tellen niet mee.

Alle drie de pogingen zijn verwijderd in plaats van blijven staan. De belofte van de
allowlist is daarmee NIET machinaal geborgd.

De drie faalwijzen hebben een gemeenschappelijke vorm die het opschrijven waard is: **te
grof gekoppeld.** Bestand in plaats van functie, string in plaats van klasse, import in
plaats van planning. Elke reparatie loste de vorige op en introduceerde de volgende laag.

---

## Trainingssamenvatting

**Actor:** eindgebruiker (D1) en het platform zelf (D2, D3).

**Voorwaarde:** een geldig JWT dat is ingetrokken (D1); een agenda-integratie met een
webhook (D2); kritieken ouder dan 180 dagen (D3).

**Actie:** uitloggen en daarna het oude token opnieuw gebruiken (D1); een agenda-wijziging
die een webhook afvuurt (D2); het verstrijken van de bewaartermijn (D3).

**Systeemreactie:** het token wordt geweigerd; de synchronisatie wordt door een worker
opgepakt; de kritieken worden dagelijks om 03:05 UTC opgeruimd.

**Succes:** een ingetrokken token geeft 401; de agenda blijft synchroon; `agent_critiques`
groeit niet onbegrensd.

**Fout:** bij een databasefout op het intrekpad wordt het token als geldig behandeld --
dat is onveranderd en valt buiten deze wijziging.

**Uitzonderingen:** `audit_logs` blijft bewust tenant-overstijgend leesbaar.
`execute_workflow_task` heeft nog steeds geen consument (D2b).
