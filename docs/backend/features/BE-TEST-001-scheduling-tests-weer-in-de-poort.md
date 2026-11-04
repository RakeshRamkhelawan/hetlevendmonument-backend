# BE-TEST-001 -- Het scheduling-domein draait weer in de blokkerende poort

ID:            BE-TEST-001
Datum:         2026-09-14
Sprint:        Poort-integriteit, dag 1 van 2
ADR:           ADR-036 (OP-196), ADR-005 (tenantisolatie -- wat de herstelde tests toetsen)
Basiscommit:   ab5d6eb0 (merge van develop c42f8e7c in iter/poort-integriteit)
OP-nummer:     OP-196 (blijft OPEN -- 130 van de 180 staan nog uit)

## Probleem

De blokkerende poort (`tests/unit tests/architecture tests/core tests/contracts`) verzamelde
16.837 tests en zag er gezond uit. Daarvan stonden er **180 onvoorwaardelijk uit**, over 21
bestanden -- geen `skipif` op een echte voorwaarde, maar een kale `@pytest.mark.skip`.

Vijftig daarvan lagen in het scheduling-domein:

| Bestand | Uit | Opgegeven reden |
|---|---|---|
| `tests/unit/test_scheduling/test_services.py` | 16 | deels "Test passes individually - skipping for batch run", deels geen |
| `tests/unit/test_scheduling/test_integrations.py` | 14 | geen enkele reden |
| `tests/unit/test_scheduling/test_repository.py` | 12 | "Test passes individually - skipping for batch run" |
| `tests/unit/test_scheduling/test_rate_limiting.py` | 5 | deels dezelfde tekst, deels geen |
| `tests/unit/scheduling/test_outlook_calendar_provider.py` | 3 | "respx URL matching complexity" / "respx PATCH mocking complexity" |

Onder de uitgezette tests zitten tenantisolatietests uit ADR-005
(`test_get_by_id_wrong_tenant_returns_none`, `test_tenant_isolation_constraints`,
`test_get_by_user_tenant_isolation`). Die draaiden nergens.

## Diagnose

**De reden-teksten waren achterhaald, niet onwaar-op-het-moment-van-schrijven.** Twee
volledige poortruns onder identieke omstandigheden op 22b7d658 (2026-09-12):

| Run | Uitkomst |
|---|---|
| ongewijzigd | `1 failed, 16495 passed, 221 skipped, 19 xfailed, 4 errors in 894.57s` |
| 48 markers weg uit de vier `test_scheduling`-bestanden | `1 failed, 16542 passed, 174 skipped, 19 xfailed, 4 errors in 621.82s` |

Delta: passed +47, skipped -47, failed ongewijzigd, nul gecrashte workers. Alle 47 slagen
gewoon in de volle suite met `-n 4`. De gedeelde toestand waarover de reden-teksten spraken
is ergens tussen toen en nu opgelost; niemand heeft de skips teruggedraaid.

**De drie respx-tests waren een ander geval: ze hadden GEEN BODY.** Een AST-scan over alle 21
bestanden vond vijf uitgezette tests die uit niets dan een docstring bestaan; drie ervan
stonden hier. De skip weghalen zou ze groen maken en het ratchetgetal verlagen zonder een
regel dekking toe te voegen.

**De opgegeven reden voor die drie was bovendien technisch onjuist.** respx 0.23.1 (exact
gepind in `requirements-test.txt:32`) heeft een `params`-patroon met `contains`-lookup voor
querystring-matching, `side_effect=[...]` voor opeenvolgende antwoorden, en een gewone
`respx.patch()`. Precies de drie dingen die volgens de reden-teksten niet konden.

## Oplossing

1. **48 skip-markers verwijderd** uit de vier `test_scheduling`-bestanden (47 tests; regel 77
   en 78 van `test_repository.py` droegen twee identieke markers op dezelfde test).
2. **Drie lege tests geschreven** in `test_outlook_calendar_provider.py`:
   - `test_list_events_success` -- matcht op `params__contains={"$top": "100"}` en toetst de
     vertaling naar `ExternalEvent` (titel, tijden, locatie, organisator, deelnemers);
   - `test_list_events_pagination` -- `side_effect=[pagina1, pagina2]` op een route, toetst dat
     de lus `@odata.nextLink` volgt en de `@odata.deltaLink` van de LAATSTE pagina teruggeeft;
   - `test_update_event_success` -- `respx.patch()`, toetst dat de titel in de verzonden body
     staat.
3. **Module-constante `_BEARER`** toegevoegd in plaats van een letterlijke
   `access_token="..."`-toewijzing: de secrets-scanner in `.claude/hooks/scan-secrets.sh`
   herkent die vorm als mogelijk credential. De hook is niet omzeild; de code is aangepast.
4. **Basislijn bijgewerkt** in `scripts/disabled_tests_baseline.json`: 180 -> 130, met de vijf
   bestanden uit de per-bestand-tabel verwijderd.

## Mutatiebewijs, beide richtingen

Elke nieuwe test is GEZIEN sterven onder de mutatie die hij hoort te vangen. Gemeten, niet
geschat; bron daarna teruggezet uit een kopie (`git diff --stat` leeg).

Elke test noemt een OPPERVLAK (querystring, gevolgde URL, PATCH-body, auth-header), en de
aanscherping van 2026-08-14 in `quality-gates.md` eist een mutatie per ELEMENT daarvan. De
eerste ronde had er een per test; de Gate 2-review toonde met vier overlevende mutaties aan
dat dat te weinig was. Dit is de tweede ronde.

| Mutatie in `src/core/scheduling/integrations/outlook_calendar.py` | Uitkomst |
|---|---|
| venster (`startDateTime`/`endDateTime`) uit de opgebouwde URL | ROOD |
| `headers = {"Authorization": ...}` -> `headers = {}` | ROOD |
| `nextLink` gevolgd met het pad zonder `$skiptoken` | ROOD |
| `title=item.get("subject", ...)` -> `title="VERMINKT"` | ROOD |
| `client.patch(` -> `client.post(` | ROOD |

Tegenrichting: ongemuteerd draait het bestand `14 passed` -- een legitiem geval blijft groen.
Bron na afloop teruggezet; `git diff` op de provider is leeg.

Twee productiedefecten kwamen uit dit werk en zijn BEWUST niet hier gefixt, elk met een eigen
registerrij en meting: **OP-238** (de tijdzone uit de Graph-payload wordt weggegooid; 13 uur
mis bij Pacific/Auckland) en **OP-239** (`isoformat()` ongecodeerd in de querystring, dus
`+00:00` komt aan als een spatie). Beide zijn gedragswijzigingen in productiecode die een
meting tegen een echte tenant verdienen, niet een bijvangst van een un-skip-ronde.

## Verificatie

- Gericht: `python -m pytest tests/unit/test_scheduling/ -q -p no:randomly` -> `181 passed`,
  nul skips.
- Gericht: `python -m pytest tests/unit/scheduling/test_outlook_calendar_provider.py -q` ->
  `14 passed`, nul skips.
- Volledige poort: zie de vergelijkingstabel in de reviewnotitie
  `docs/backend/review/review-BE-TEST-001.md`.

## Trainingssamenvatting

- Actor: een ontwikkelaar of CI-runner die de blokkerende poort draait.
- Voorwaarde: de wijziging staat op de tak en `scripts/disabled_tests_baseline.json` staat op 130.
- Actie: `python -m pytest tests/unit tests/architecture tests/core tests/contracts -n 4`, gevolgd
  door `python scripts/count_disabled_tests.py` (met `DATABASE_URL` gezet, anders is de collectie
  onvolledig).
- Systeemreactie: de vijftig herstelde tests draaien mee in plaats van te worden overgeslagen;
  de ratchet meldt `130 over 16 bestanden -- gelijk aan de basislijn` en eindigt met exit 0.
- Succes: nul nieuwe failures ten opzichte van de referentierun, en het aantal geslaagde tests is
  gestegen met de vijftig herstelde tests.
- Fout: draait iemand de poort zonder `DATABASE_URL`, dan stopt de ratchet expliciet met
  "COLLECTIEFOUT ... de telling is onvolledig" in plaats van stil te laag te tellen.
- Uitzonderingen: in een `git worktree` zonder `.env` falen vijf tests om omgevingsredenen
  (`SECRET_KEY`-placeholder plus vier collectiefouten in `test_snapshot_security.py`). Dat zijn
  geen bevindingen; ze staan aan beide kanten van elke vergelijking gelijk.

## Wat bewust NIET is gedaan

- **De overige 130 uitgezette tests.** Het auth- en tenantcluster (39 tests over vier
  bestanden) raakt de oppervlakte die het P0-autorisatiecluster deze week verbouwt; die komen
  op dag 2, na de merge van dat cluster. De resterende bestanden zijn een eigen ronde.
- **De 55 skips met de tekst "Flaky: ... shared state".** Die zitten grotendeels in het
  auth-cluster en hebben, anders dan het scheduling-cluster, wel een concreet vermoeden van
  echte testvervuiling. Niet vermengen met deze dag.
- **OP-227** (de schematoets zit niet in `pre-deploy-check.sh`): dag 2.
