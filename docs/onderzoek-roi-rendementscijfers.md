# Onderzoek: rendementscijfers (ROI) per agent-run

Datum: 2026-10-10. Rol: vraag (alleen lezen en meten, niets gewijzigd).
Gemeten op `develop` @ 756e9f56. Alembic-head: `20261009_user_roles_tenant_id` (een head,
gemeten met `alembic -c src/alembic.ini heads`; niet geupgraded).

## Kern in vijf zinnen

1. De ROI-keten is op DRIE plekken stuk, niet op een: de tabel bestaat niet, de route wordt
   niet geladen, en de frontend verwacht andere velden dan de backend geeft.
2. De "besparing" die de code zou tonen is geen meting maar een vast getal per pack
   (bijv. 120 minuten per run voor `mkb.zero_admin`) maal 75 euro per uur, verborgen in code.
3. De markt (UiPath, Power Automate) doet in de kern hetzelfde, maar laat de KLANT de
   handmatige tijd en het uurtarief invullen en telt alleen gelukte runs.
4. Juridisch: wie een besparingscijfer toont, moet het kunnen bewijzen (art. 6:195 BW);
   ROI per medewerker is monitoring (OR-instemming art. 27 lid 1 sub l WOR, AVG).
5. Advies: hergebruik niets bestaands als ROI-tabel, maak een kleine eigen tabel per run
   zonder medewerkersgegevens, en toon besparing alleen met de aanname ernaast, door de
   klant ingesteld.

## 1. Stand in de code

### Schrijvers en lezers

| Wat | Plek | Bevinding |
|---|---|---|
| Schrijver | `src/core/als/enterprise/packs.py:432-469` | `_run_single_step` roept na een gelukte stap `ROIService.log_execution` aan, in `best_effort`; velden: tenant_id, agent_id, pack_id, task_id, phase=`"act"`, duur in seconden |
| Schrijf-SQL | `src/core/analytics/roi_service.py:94-114` | rauwe `INSERT INTO agent_execution_logs`, met eigen `commit()` |
| Lees-SQL | `src/core/analytics/roi_service.py:41-80` | telt `COUNT(DISTINCT task_id)` per pack waar `phase='act'` |
| Aannames | `src/core/analytics/roi_service.py:25-36` | `BASELINES` (minuten per pack: monthly_close 480, mkb.zero_admin 120, zzp.tax_survival 180, default 30) en `AVG_HOURLY_RATE = 75.0` -- hard in code, niet per tenant, nergens onderbouwd |
| Uitvoerveld | `src/core/analytics/roi_service.py:12-16` | `ROISummary`: total_time_saved_hours, total_cost_reduced, pack_breakdown |
| Route | `src/core/api/v1/analytics.py:63-75` | `GET /roi`, tenant uit `get_tenant_id` (goed) |
| Tabel | -- | `agent_execution_logs` staat in geen model en geen migratie (`git grep` op src: alleen de rauwe SQL) |

### Twee nieuwe vondsten (gemeten)

**A. De route `/roi` wordt nooit geladen.** Er bestaan zowel `src/core/api/v1/analytics.py`
als het pakket `src/core/api/v1/analytics/`. Python laadt dan het pakket. Gemeten:

```
python -c "import src.core.api.v1.analytics as m; print(m.__file__); print([r.path for r in m.router.routes])"
-> ...\analytics\__init__.py
-> alleen /analytics/benchmarks/... (zes routes, geen /roi)
```

`src/core/api/registries/analytics.py:11` importeert precies die `router`. Dus ook met een
tabel geeft `/api/v1/analytics/roi` nu niets terug. Niet gemeten tegen een draaiende app.

**B. Frontend en backend spreken elkaar tegen.**

| Plek | Verwacht |
|---|---|
| `frontend/src/types/analytics.ts:158-166` | totalSavings, automatedTasks, manualTasksPrevented, timeSavedMinutes, costPerHour, breakdown.byDepartment |
| `frontend/src/services/analyticsService.ts:79-87` (tweede, ander type) | total_savings, time_saved_hours, efficiency_gain_pct, cost_per_task, tasks_completed |
| backend `ROISummary` | total_time_saved_hours, total_cost_reduced, pack_breakdown |

Bovendien stuurt `frontend/src/services/analytics/AnalyticsService.ts:25-26` `tenant_id` als
queryparameter mee. De backend negeert hem (tenant komt uit JWT), maar het is in strijd met
de NOOIT-regel en hoort weg. Scherm: `frontend/src/components/analytics/AnalyticsDashboard.tsx:250-380`
(tegels "besparing", "taken", "tijd bespaard", "voorkomen handwerk", uitsplitsing per afdeling).

### Tests

- `tests/unit/analytics/test_roi_logic.py:5-20` -- mock-db, toetst de rekensom, niet de tabel.
- `tests/unit/als/enterprise/test_pack_orchestrator_execute_step.py:329,359` -- patcht ROIService.
- `tests/unit/enterprise/test_pack_invoer_komt_bij_de_stap_aan.py:83-114,217,380` -- bewaakt dat
  een kapotte ROI-log de stap niet laat falen.
- `tests/integration/test_packs_execute_route.py:542-548` -- idem, trage ROI-log.
- Frontend: `AnalyticsDashboard.test.tsx`, `useAnalytics*.test.ts` -- alles op gemockte data.
- Geen enkele test leest echte ROI uit een echte database. Daarom bleef dit onzichtbaar.

### Bestaande tabellen die je zou kunnen hergebruiken

| Tabel | Plek | Geschikt? |
|---|---|---|
| `usage_records` | `src/core/models/usage_models.py:11-44`, migratie `20260817_baseline_ontbrekende_tabellen.py:119` | Bedoeld voor facturering/quota (metric_type + value + JSON). tenant_id NOT NULL. Heeft een `user_id` -- dat is precies het medewerkersveld dat je bij ROI NIET wilt. Generiek JSON = geen schema voor aannames. Niet hergebruiken als ROI-bron; wel kan elke run er een `agent_run`-teller in zetten voor quota. |
| `workflow_executions` | `src/core/models/workflow_models.py:235` | Voor workflowbuilder-runs, niet voor pack-stappen. |
| `pack_usage_aggregates` | `src/core/database/models/analytics.py:55` | Geanonimiseerde sector-benchmark, geen tenant-data per run. |
| `budget_usage`, `tenant_llm_budget` | `src/core/agents/budget_manager.py:96`, `src/core/learning/twin_models.py:390` | LLM-kosten/budget; mogelijke bron voor "kosten per run". Niet gemeten of pack-stappen hier schrijven. |

## 2. Wat de markt doet

- **UiPath Insights / Automation Hub**: tijd bespaard = (runs x handmatige tijd) - (runs x
  robottijd). De handmatige tijd komt uit een assessment door de klant, en mag bewust op
  minder dan 100% gezet worden ("final manual time saved per run").
  https://docs.uipath.com/automation-hub/automation-cloud/latest/user-guide/execution-assessment ,
  https://docs.uipath.com/insights/standalone/2022.4/user-guide/templates
- **Microsoft Power Automate "Savings"**: per flow een door de gebruiker ingestelde
  "saving rule" (minuten en/of geld per run); alleen GELUKTE runs tellen, testruns niet.
  https://learn.microsoft.com/en-us/power-automate/savings
- **Zapier en vergelijkbare**: frequentie x handmatige minuten; marketing-schattingen, geen
  meting. (secundaire bron) https://www.lowcode.agency/blog/why-your-business-needs-zapier-automation
- **Kritiek op AI-agent-ROI**: tijdwinst wordt makkelijk overschat -- toezicht, nakijken en
  herstelwerk worden weggelaten, en de nulmeting wordt vaak pas NA invoering gedaan.
  https://www.mindstudio.ai/blog/calculating-ai-agent-roi ,
  https://gloat.com/blog/measure-hr-ai-agent-roi/ ,
  https://evals.alignment.org/notes/2026-02-17-exploratory-transcript-analysis-for-estimating-time-savings-from-coding-agents/
- Uit eigen kennis, NIET opgehaald deze sessie: het METR-onderzoek (juli 2025) waarin
  ervaren ontwikkelaars dachten ~20% sneller te zijn met AI en gemeten ~19% trager waren.
  Verifieer voor gebruik.

Gemene deler: niemand MEET bespaarde tijd. Iedereen telt runs en vermenigvuldigt met een
aanname. De nette spelers laten die aanname door de klant zetten en tonen haar.

## 3. Risico's

**Eerlijkheid / misleiding.** Een vast getal in code ("deze run bespaarde 2 uur, 150 euro")
dat de klant niet ziet en niet zelf koos, is een claim van ons. Bij een geschil ligt de
bewijslast voor juistheid bij wie de uiting deed (art. 6:195 BW, bij misleidende reclame
art. 6:194 BW; geldt ook tussen bedrijven).
https://wetboekplus.nl/burgerlijk-wetboek-boek-6-artikel-195-bewijslast/
De ACM-lijn (voor duurzaamheid uitgewerkt, als denkkader bruikbaar): juist, specifiek,
onderbouwd, actueel. https://www.acm.nl/nl/publicaties/acm-vernieuwde-leidraad-biedt-meer-duidelijkheid-over-misleidende-vage-duurzaamheidsclaims
Niet onderzocht: of een ROI-tegel in een betaald product juridisch "reclame" is. Behandel
hem alsof.

**AVG en OR.** ROI per medewerker (wie startte de run, hoeveel "bespaarde" die persoon) is
gegevens over prestaties van personeel. Een regeling die geschikt is om prestaties te
volgen vraagt OR-instemming (art. 27 lid 1 sub l WOR) en een AVG-grondslag (art. 88 AVG
voor de arbeidsverhouding). Dat legt een last bij de KLANT die hij niet verwacht.
https://www.awvn.nl/medezeggenschap/hr-van-a-tot-z/or-en-privacy/ ,
https://www.rendement.nl/or-en-digitale-veiligheid/nieuws/ap-ondersteunt-or-in-rol-bewaking-privacy.html
Extra voor de HR-pack: reskilling/termijnbewaking gaat al over medewerkers; koppel ROI daar
zeker niet aan personen.

**Techniek.** Rauwe SQL buiten de ORM ontloopt de `do_orm_execute`-tenanthook (nu wel met
handmatige WHERE); een eigen `commit()` midden in een stap; tabel zonder RLS-beleid.

## 4. Advies

### Wat per agent-run vastleggen (nieuwe tabel, bijv. `agent_run_outcomes`)

| Veld | Waarom |
|---|---|
| id | |
| tenant_id INTEGER NOT NULL, FK tenants, RLS | tenant-isolatie |
| pack_id, agent_id, task_id | wat liep er |
| status (`geslaagd`/`mislukt`/`time-out`/`wacht_op_mens`) | alleen geslaagd telt als besparing; mislukt telt als kosten |
| started_at, finished_at (timezone-aware) | doorlooptijd, gemeten |
| needed_human_review (bool) | eerlijkheid: menselijk nakijkwerk is geen nul |
| items_processed (int, nullable) | bijv. 12 aanmaningen; besparing per item is eerlijker dan per run |
| llm_cost_eur (numeric, nullable) | aftrekpost; bron `budget_usage` als die al gevuld wordt (niet gemeten) |
| created_at | |

NIET: user_id, naam, e-mail, of iets dat de run aan een medewerker koppelt. Wie de run
startte staat al in de audittrail; de ROI-tabel heeft het niet nodig.

Waarom geen hergebruik: `usage_records` is voor facturering, heeft `user_id` en ongetypeerde
JSON; een kolom erbij maakt facturering en rendement van elkaar afhankelijk. Een kleine
eigen tabel met ORM-model + migratie met werkende `downgrade()` is eenvoudiger te testen
(isolatietest A/B). Dit is een nieuwe tabel, geen DROP: geen interlock 1, wel `/migration`.

### Aanname apart en door de klant ingesteld

Tabel `roi_assumptions` per tenant per pack: `manual_minutes_per_item`, `hourly_rate_eur`,
`set_by_role`, `set_at`, `source` (`klant_ingevuld` / `standaard_voorstel`). De huidige
`BASELINES` worden hooguit een voorstel dat de klant moet bevestigen.

### Rekenen en tonen

- Besparing = geslaagde items x handmatige minuten (klant) - menselijke nakijktijd (indien
  gelogd) ; euro's = uren x uurtarief (klant) - LLM-kosten.
- Toon twee lagen: (1) GEMETEN: aantal runs, geslaagd/mislukt, items, doorlooptijd, kosten;
  (2) GESCHAT: tijd en euro's, altijd met de zin "geschat op basis van uw instelling:
  X minuten per aanmaning, Y euro per uur" en een link om die te wijzigen.
- Geen aanname ingevuld: toon alleen laag 1, geen euro's.
- Alleen per tenant en per pack, nooit per medewerker of per afdeling (de huidige
  `byDepartment`-uitsplitsing schrappen).

### Minimale pilotversie

Laag 1 (gemeten aantallen) plus een instelbare aanname per pack. Dat is verdedigbaar, en
het is wat UiPath en Microsoft in de kern ook doen.

### Wat NIET doen

- Geen vaste minuten of uurtarief in code als "besparing" tonen.
- Geen ROI per persoon of afdeling.
- Geen "voorkomen handwerk"/"efficientie %" zonder nulmeting.
- `usage_records` niet als ROI-bron misbruiken.
- Geen rauwe SQL en geen eigen `commit()` in de stap; schrijven blijft in `best_effort`.
- `tenant_id` niet meer als queryparameter vanuit de frontend sturen.

### Volgorde voor een bouwbrief

1. Routeschaduw oplossen (`analytics.py` vs `analytics/`) met een test die `/api/v1/analytics/roi` in de app-routes eist.
2. Model + migratie + isolatietest; schrijver in `packs.py` omzetten.
3. Aannametabel + beheerscherm.
4. Een frontendtype (twee concurrerende `ROIMetrics` samenvoegen) en de tegels herschikken.
5. Acceptatie met beeld tegen `docs/meetlat.md`.

## Niet gemeten

- `/roi` tegen een draaiende applicatie (alleen de router geimporteerd).
- Of pack-stappen nu iets naar `budget_usage`/`tenant_llm_budget` schrijven.
- Of er al een scenario voor ROI in `docs/meetlat.md` staat (niet gelezen).
- Juridische toets door een jurist; bronnen zijn wettekst-sites en brancheartikelen.
