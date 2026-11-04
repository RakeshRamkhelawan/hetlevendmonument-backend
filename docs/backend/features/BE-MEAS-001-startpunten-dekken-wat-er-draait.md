# BE-MEAS-001 -- De startpunten dekken wat er werkelijk draait

Status:   GELEVERD
Datum:    2026-09-26
Basis:    develop `1d87a070`
Domein:   meetgereedschap (`scripts/codebase_inventory.py`)
Ernst:    HOOG -- de meting stuurde de prioriteiten, en hij was fout

---

## 1. De bevinding

`scripts/codebase_inventory.py` deelt `src/` in bereikbaar en onbereikbaar op basis van een
lijst startpunten. Die lijst stond op drie modules:

```python
# scripts/codebase_inventory.py:53, zoals het stond op 1d87a070
ROOTS = ["src.main", "src.core.app_factory", "src.core.app_lifespan"]
ROOT_PREFIXES = ["src.core.tasks."]
```

Er worden er ACHT gestart. De vijf die ontbraken, met vindplaats:

| Module | Waar hij wordt gestart |
|---|---|
| `src.workers.workflow_worker` | `docker-compose.yml:224`, `Dockerfile:168` (dramatiq-broker) |
| `src.workers.actors` | zelfde regel (het actormodule) |
| `src.workers.scheduler` | `docker-compose.yml:268`, `docker-compose.prod.yml:195` (`python -m`) |
| `src.core.learning.worker` | `docker-compose.yml:405`, `.dev.yml:136`, `.prod.yml:140` |
| `src.alembic.env` | `alembic upgrade head` in beide entrypoint-scripts |

## 2. Wat het kostte

**34 modules stonden als DOOD geboekt terwijl ze draaien.** De zwaarste:

```text
662 regels  GEEN test  src/workers/scheduler.py
248 regels  GEEN test  src/alembic/env.py
222 regels  GEEN test  src/core/models/campaign_models.py
149 regels  GEEN test  src/core/database/import_all_models.py
```

Vijftien van de 34 hebben geen enkele test (1.832 regels); negentien wel. Dat laatste is op
zichzelf een signaal: er stond testcode voor modules die het instrument dood noemde.

Het mechanisme achter de meerderheid: `alembic/env.py` importeert `import_all_models.py`, dat
elk databasemodel binnenhaalt. Zonder alembic als startpunt stond de hele modellaag als dood.

**Waarom dit de gevaarlijkste vorm van een verkeerde meting is in dit project:**
"onbereikbaar" leest als "mag weg", en de prioriteiten voor het testwerk worden erop
gebaseerd. `src/workers/scheduler.py` is 662 regels, draait als eigen container in productie,
heeft nul tests -- en stond op de stapel "dode ballast, later opruimen".

## 3. De gecorrigeerde kaart

| | modules | regels | was |
|---|---|---|---|
| bereikbaar EN getest | 741 | 205.521 | 722 |
| **draait zonder test** | **713** | **91.036** | 698 |
| onbereikbaar maar wel getest | 295 | 78.381 | 314 |
| onbereikbaar EN ongetest | 530 | 95.950 | 545 |

Onbereikbaar totaal: 859 (37%) -> **825 (36%)**.

De API-laag verandert NIET: 333 modules, 40.470 regels, 561 endpoints. Geen van de 34 zat
daarin, dus `docs/agent-briefs/API-LAAG-MASTERPROMPT.md` blijft kloppen.

## 4. Bijvangst -- drie Dockerfiles zonder startbestand

`src/core/agents/{diagnostics,knowledge,sentiment}_agent/Dockerfile` draaien alle drie
`CMD ["python", "main.py"]`. Die `main.py` bestaat NIET (`git ls-files` geeft nul treffers) en
geen enkel compose-bestand verwijst naar die images. Dode configuratie, geen startpunt. Niet
opgeruimd in deze knip -- het is een aparte beslissing of die mappen weg kunnen, en de
bewaker hieronder wordt er niet rood van.

## 5. De bewaker

`tests/architecture/test_de_startpunten_dekken_wat_er_echt_draait.py` eist dat elk proces dat
wij starten in `ROOTS` staat. Bronnen:

- **compose-bestanden** -- via de YAML-STRUCTUUR (`services.*.command` / `.entrypoint`), niet
  als tekstzoekopdracht;
- **Dockerfiles en entrypoint-scripts** -- regelgebaseerd, want daar is geen structuur;
- **alembic** -- apart, want `alembic -c <pad>/alembic.ini upgrade head` noemt zijn env-module
  nergens. De koppeling staat in `script_location` in dat ini-bestand.

Een kandidaat telt alleen als er echt een `.py`-bestand bij hoort. Dat maakt van een
tekstreffer een structurele toets.

**Mutatiebewijs, zes stuks:**

| # | Mutatie | Uitkomst |
|---|---|---|
| P1 | `src.workers.scheduler` uit ROOTS (de echte bevinding) | ROOD |
| P2 | `src.core.learning.worker` uit ROOTS | ROOD |
| P3 | `src.alembic.env` uit ROOTS (toetst de ini-afleiding) | ROOD |
| P4a | ruis `src.verzonnen.module` in een `ENTRYPOINT`-regel | GROEN -- genegeerd |
| P4b | dezelfde ruis, maar zonder de bestandstoets | ROOD -- vals alarm |
| P5 | een startpunt dat niet bestaat toegevoegd | ROOD |
| P6 | TEGEN: een startpunt dat NIET gestart wordt | GROEN |

P6 is de tegenrichting: de bewaker toetst gestart-in-ROOTS en niet andersom. `app_factory` en
`app_lifespan` staan er terecht in zonder zelf een proces te zijn.

## 6. Twee fouten van mezelf, gevonden door het mutatiebewijs

**De eerste versie van de docstring beweerde iets onwaars.** Er stond dat de bestandstoets
`src/alembic.ini` wegfiltert. Dat kan niet: daar staat een schuine streep en de regex eist een
punt, dus die kandidaat ontstaat nooit. Gemeten: de toets filtert vandaag NIETS weg (5
kandidaten voor, 5 na). Hij is wel dragend -- P4 toont dat in twee delen aan -- maar de reden
die erbij stond klopte niet. Dit is exact wat `.claude/rules/quality-gates.md` verbiedt onder
"Een onbewezen oorzaak wordt nooit een WHY-comment".

**En mutatie P4 zelf was eerst ongeldig.** Ik zette de ruis in een `#`-comment, en de scanner
slaat commentaarregels over. De mutatie bewees dus niets en bleef groen.

## 7. Verificatie

```text
architectuur + scripts : 1209 passed, 0 failed
inventarisatie         : 859 -> 825 onbereikbaar, 698 -> 713 draait-zonder-test
mutaties               : 6 van 6
ruff                   : All checks passed
```

## 8. Wat NIET is gedaan

- **De 15 nieuw-zichtbare modules zonder test krijgen geen tests in deze knip.** Ze horen nu
  in de juiste groep en dat was het doel. `src/workers/scheduler.py` (662 regels, eigen
  container, nul tests) verdient een eigen knip en staat daarmee hoog op de lijst.
- **De drie dode agent-Dockerfiles blijven staan** (paragraaf 4).
- **De heuristiek blijft ruimhartig.** 825 is een ondergrens, geen exact getal.

---

## Trainingssamenvatting

### Stroom 1 -- meten hoeveel code er dood is

- Actor: een sessie die wil weten waar het testwerk moet beginnen.

- Voorwaarde: `scripts/codebase_inventory.py` kent elk proces dat wij starten.

- Actie: `python scripts/codebase_inventory.py`.

- Systeemreactie: het script loopt vanaf elk startpunt door de importgraaf en meldt hoeveel
  modules daarvandaan niet te bereiken zijn.

- Succes: een getal dat je kunt vergelijken met dat van vorige week.

- Fout: ontbreekt er een startpunt, dan wordt draaiende code als dood geteld. Het script
  meldt dat NIET -- het geeft gewoon een te hoog getal. Daarom staat er een bewaker op.

- Uitzonderingen: de heuristiek is ruimhartig en verklaart eerder iets bereikbaar dan dood.
  Het getal is een ondergrens.

### Stroom 2 -- een nieuw proces toevoegen aan de applicatie

- Actor: een ontwikkelaar die een worker, een scheduler of een taak toevoegt.

- Voorwaarde: het proces wordt gestart vanuit een compose-bestand, een Dockerfile of een
  entrypoint-script.

- Actie: het startcommando toevoegen en committen.

- Systeemreactie: `test_de_startpunten_dekken_wat_er_echt_draait.py` wordt ROOD, met de
  modulenaam in de melding.

- Succes: je voegt die module toe aan `ROOTS` in `scripts/codebase_inventory.py`, met de
  vindplaats erbij, en de bewaker wordt groen.

- Fout: negeer je hem, dan telt alles wat jouw proces importeert vanaf dat moment als dode
  code -- en dat leest als "mag weg".

- Uitzonderingen: start je iets buiten compose, Dockerfile of entrypoint-script om (een
  cronjob op de host, een handmatig commando), dan ziet de bewaker het niet. Zet het dan zelf
  in `ROOTS` met de reden erbij.
