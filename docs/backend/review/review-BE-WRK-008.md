# Backend Feature Review -- BE-WRK-008

## Metadata

- **Review ID:** review-BE-WRK-008
- **Feature ID:** BE-WRK-008
- **Feature naam:** APScheduler TaskScheduler met foutmelding en broker-bewaking
- **Reviewer:** sanskritisetu-org-7f (regie, Gate 2)
- **Datum:** 2026-09-26
- **Spec versie:** 1.0

---

## A. Eindoordeel

STATUS: APPROVED WITH MINOR GAPS

De implementatie is correct, de architectuurbewakers dekken de risico's, en alle 15 tests
slagen. De regie heeft items A t/m H als CHANGES_REQUESTED ingediend; allemaal opgelost
in commit a43e58ba. Twee minor gaps hieronder.

---

## B. Taak 7 teruggedraaid -- reden en consequentie voor toekomstige sessies

**Taak 7 (SQLAlchemyJobStore voor persistente jobs) is teruggedraaid. Dit is geen uitstel.**

Gemeten faalvorm: APScheduler pickling werpt `TypeError: Schedulers cannot be serialized`
zodra een `_run_*`-methode via een persistente jobstore wordt opgeslagen. De oorzaak: de
methode is een bound method van `TaskScheduler`, en `self` houdt het `scheduler`-object
vast. Pickle kan `AsyncIOScheduler` niet serialiseren.

De workaround die werd geprobeerd (`__getstate__`/`__setstate__` om `self.scheduler` uit
het pickle-baar domein te houden) loste het pickle-probleem deels op maar creeerde een
nieuw risico: na een deserialisatie had de methode geen `scheduler`-referentie meer, en
elke poging hem daarna opnieuw te binden was niet eenduidig getoetst.

**De echte oplossing vereist module-level functies** die via een tekstuele referentie
(string, niet object) aan de jobstore worden doorgegeven. APScheduler deserialiseert die
string bij herstel en zoekt de functie op in het module-namespace -- zonder `self`.
Die refactor is groter dan de taak toestond en vereist dat de `_run_*`-architectuur
VOOR de jobstore wordt omgebouwd.

**Waarschuwing voor de volgende sessie die persistentie wil toevoegen:**
- De architectuurtest (`test_scheduler_geen_stille_except.py`) toetst methoden van de
  klasse `TaskScheduler` via `knoop.body`. Als de `_run_*`-methodes naar module-niveau
  verhuizen, vindt de test 0 methodes en faalt de count-assertie (>= 16) -- de test wordt
  dan rood, niet stilletjes groen. Dat is opzettelijk.
- Begin bij de module-level functie-refactor, niet bij de jobstore-configuratie. Een
  groene guard die 0 functies bewaakt is hetzelfde als geen guard.

## C. Samenvatting

Taak 7 teruggedraaid (zie sectie B). Overgebleven kern: MemoryJobStore, 16 terugkerende
jobs, listener voor fouten en gemiste uitvoeringen, broker-bewaking bij start. De
architectuurtest voor stille excepts gebruikt expliciete recursie (na regie-feedback C);
de count-assertie (>= 16) voorkomt stille blindheid bij een toekomstige refactor.

---

## D. Bevindingen per categorie

### 1. Regie-items (A t/m H) -- allemaal opgelost

- A (non-ASCII): opgelost -- geen accent-tekens meer in scheduler.py of test_gedrag.py
- B (Any-ratel): opgelost -- event: JobEvent via TYPE_CHECKING; baseline 7050->7049
- C (ast.walk): opgelost -- expliciete recursie; contextlib.suppress en best_effort als
  verboden vormen toegevoegd
- D (count-asserties): opgelost -- >= 16 methodes; git ls-files-asserties aanwezig
- E (raise-pad test): opgelost -- T3b met P1/P2/P3
- F (globale broker): opgelost -- check aan het begin van _eis_een_echte_broker()
- G (DATABASE_URL): n.v.t. na taak 7 revert
- H (import-volgorde, noqa, typos): opgelost

### 2. Minor gaps

- **LOW** -- De docstring in `_eis_een_echte_broker()` vermeldt "beide UITGEVOERD" voor
  het mutatiebewijs, maar de raise-pad zelf was pas getoetst na de Gate 2-ronde (item E).
  De docstring klopt nu (T3b P1 bewijst de raise-pad), maar was op het moment van de eerste
  commit al verouderd. Geen productie-impact.
- **LOW** -- `SQLAlchemyJobStore` (taak 7) is teruggedraaid; als persistentie van
  geplande jobs later alsnog nodig is, vereist dat een aparte ADR-beslissing over de
  pickle-oplossing (module-level functies of celery-achtige aanpak).

---

## E. Verificatie

- 15 tests: 15 passed (test_scheduler_gedrag.py x12, test_scheduler_geen_stille_except.py x1,
  test_de_startpunten_dekken_wat_er_echt_draait.py x2)
- 54 gerichte tests via pre-commit hook: 54 passed
- mypy: 0 issues op src/workers/scheduler.py
- pyright: 0 errors op src/workers/scheduler.py
- ruff: all checks passed
- Any-baseline: 7050 -> 7049 (verbeterd, vastgeklikt)
- Commit: a43e58ba op iter/wrk001-planner
