# Backend Feature Specification

## Metadata

- **Feature ID:** BE-WRK-008
- **Feature naam:** APScheduler TaskScheduler met foutmelding en broker-bewaking (BE-WRK-001)
- **Status:** Geimplementeerd
- **Auteur:** sanskritisetu-org-7d
- **Reviewer:** sanskritisetu-org-7f (regie Gate 2)
- **Datum:** 2026-09-26
- **Gerelateerde user story / ticket:** BE-WRK-001 sprinttaak (taak 1-7 structuur, taak 7 teruggedraaid)
- **Gerelateerde router / module:** `src/workers/scheduler.py`, `src/workers/actors.py`
- **Gerelateerde frontend endpoints:** Geen
- **Gerelateerde database tabellen:** Geen (MemoryJobStore; SQLAlchemyJobStore teruggedraaid)
- **Versie:** 1.0

---

## Doel en scope

### Doel

Een betrouwbare APScheduler-integratie bouwen die:
1. Terugkerende beheertaken (gezondheid, retentie, audit, training) inplant.
2. Fouten en gemiste uitvoeringen zichtbaar maakt via een listener, niet stil slikt.
3. Weigert op te starten als actors nog op een StubBroker hangen (StubBroker stuurt berichten
   nergens heen).

### In scope

1. `TaskScheduler.initialize()` -- inplannen van 16 terugkerende jobs met `MemoryJobStore`.
2. `TaskScheduler._op_job_probleem()` -- listener die `EVENT_JOB_ERROR` als ERROR en
   `EVENT_JOB_MISSED`/`EVENT_JOB_MAX_INSTANCES` als WARNING logt.
3. `_bind_the_real_broker()` -- wisselt de globale Dramatiq-broker naar Redis voor start.
4. `_eis_een_echte_broker()` -- weigert met RuntimeError als de globale broker of een
   individuele actor nog op StubBroker staat.
5. `start_scheduler()` -- roept bind -> eis -> get_scheduler aan in die volgorde.
6. `shutdown_scheduler()` -- laat geen singleton achter.
7. Architectuurbewakers: `test_scheduler_geen_stille_except.py` (16 `_run_*`-methodes mogen
   geen stille except hebben), `test_de_startpunten_dekken_wat_er_echt_draait.py` (scheduler
   staat als startpunt in codebase_inventory.py).

### Out of scope

- SQLAlchemyJobStore (taak 7 teruggedraaid): APScheduler pickling van bound methods die
  `self.scheduler` bevatten geeft `TypeError: Schedulers cannot be serialized`. De
  workaround (`__getstate__`/`__setstate__`) was onvolledig; de echte fix vereist
  module-level functies, wat een grotere refactor is. Beslissing: sanskritisetu-org-7f.
- Database schema-wijzigingen.
- Frontend-wijzigingen.
- Nieuwe API-endpoints.

---

## Technische beschrijving

### Architectuur

`TaskScheduler` is een singleton via `get_scheduler()`. De scheduler draait als aparte
container (`docker-compose.yml`, service `scheduler`). `start_scheduler()` is de lifespan-
entrypoint; de container heeft geen FastAPI-app maar een eigen async main loop.

### Foutafhandeling

Elke `_run_*`-methode gooit uitzondering ongedempt; APScheduler ontvangt de uitzondering en
vuurt `EVENT_JOB_ERROR`. `_op_job_probleem()` logt die als ERROR met job-id en uitzonderings-
type. `EVENT_JOB_MISSED` en `EVENT_JOB_MAX_INSTANCES` worden als WARNING gelogd. Een
stille `except Exception: pass` of `contextlib.suppress` in een `_run_*`-methode maakt
APScheduler blind voor de fout -- bewaakt door de architectuurtest.

### Broker-bewaking

Bij start: `_bind_the_real_broker()` haalt de RedisBroker op via `get_redis_broker()`.
Daarna controleert `_eis_een_echte_broker()`:
1. Of de globale `dramatiq.get_broker()` geen StubBroker is.
2. Of geen enkele actor in `src.workers.actors` nog op StubBroker staat (actors die voor
   de bind waren geregistreerd houden het oude broker-object).

### Job-defaults

Alle jobs krijgen `misfire_grace_time=3600` (een uur uitstel), `coalesce=True` (inhaaltaak
eenmalig draaien), `max_instances=1` (geen parallelle uitvoeringen).

---

## Acceptatiecriteria

| # | Criterium | Getoetst via |
|---|-----------|-------------|
| 1 | Een falende job logt een ERROR met job-id | T1 in test_scheduler_gedrag.py |
| 2 | Een gemiste uitvoering logt een WARNING met job-id | T2 in test_scheduler_gedrag.py |
| 3 | start_scheduler() roept bind aan voor de broker-check | T3 in test_scheduler_gedrag.py |
| 4 | _eis_een_echte_broker() gooit RuntimeError bij StubBroker | T3b in test_scheduler_gedrag.py |
| 5 | get_scheduled_jobs() geeft exact de 16 ingeplande jobs | T4 in test_scheduler_gedrag.py |
| 6 | shutdown_scheduler() zet de singleton op None | T5 in test_scheduler_gedrag.py |
| 7 | Geen _run_*-methode heeft een stille except | test_scheduler_geen_stille_except.py |
| 8 | scheduler staat in codebase_inventory.py ROOTS | test_de_startpunten_dekken_wat_er_echt_draait.py |

---

## Trainingssamenvatting

### Fout in een geplande job

Actor: APScheduler
Voorwaarde: een `_run_*`-methode gooit een onbeheerde uitzondering
Actie: APScheduler vuurt `EVENT_JOB_ERROR` en roept de geregistreerde listener aan
Systeemreactie: `_op_job_probleem()` logt een ERROR-record met job-id en type uitzondering;
de volgende ingeplande uitvoering gaat gewoon door
Succes: het logrecord is aanwezig; APScheduler pakt de volgende run op
Fout: een stille `except` slikt de uitzondering -- listener krijgt nooit een signaal;
bewaard door test_scheduler_geen_stille_except.py
Uitzondering: `EVENT_JOB_MISSED` en `EVENT_JOB_MAX_INSTANCES` worden als WARNING gelogd,
niet als ERROR

### Opstarten met StubBroker-actor

Actor: scheduler-container bij start
Voorwaarde: een actor in `src.workers.actors` staat nog op StubBroker na een mislukte bind
Actie: `start_scheduler()` roept `_bind_the_real_broker()` aan, daarna `_eis_een_echte_broker()`
Systeemreactie: `RuntimeError` wordt gegoid; de container start niet
Succes: de container weigert te starten, bewijs van misconfiguratie is zichtbaar in de logs
Fout: als de StubBroker-check wordt overgeslagen, publiceert de scheduler taken die nergens
aankomen -- bewaard door de volgorde-test T3

---

## Regressierisico's

- `_eis_een_echte_broker()` kan vals alarm geven als actors VOOR de broker-wissel worden
  geregistreerd bij een toekomstige refactor. Bewaking: T3b P1.
- Als `_run_*`-methodes naar module-niveau verplaatsen, vindt de architectuurtest 0 methodes
  en faalt de count-assertie (>= 16). Dit is opzettelijk om stille blindheid te voorkomen.
