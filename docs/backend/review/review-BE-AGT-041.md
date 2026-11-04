# Review BE-AGT-041 -- manifest-budget afgedwongen

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-041 |
| Datum | 2026-08-01 |
| Reviewvorm | Zelfreview (reviewer-subagents staan deze sessie uit) |
| Omvang | ~120 regels productiecode in 3 bestanden; 11 tests |
| Uitkomst | **APPROVED** |

> **Gate 2, expliciet.** Deze wijziging is groter dan de "small fixes"-uitzondering uit
> `quality-gates.md` (>50 regels, 3 bestanden). `code-reviewer` en `quality-reviewer` zijn
> deze sessie niet inzetbaar, dus de dubbele GO is niet gehaald. Dat is een **openstaand
> punt**, geen afgevinkt vakje: bij de volgende sessie met reviewers hoort deze diff alsnog
> langs beide. Vastgelegd in plaats van weggeredeneerd.

---

## 1. Wat de wijziging waard is

Er stond een echt weglooppad open. `_parse_tool_calls()` gebruikt `finditer` zonder limiet,
`act()` voerde alles uit met 30s per tool. Vijftig directives in een enkel LLM-antwoord
betekenden vijftig uitvoeringen. Dat is geen theoretisch risico maar de reden dat D10 de rem
vóór de lus plaatst -- en de lus was er, in `act()`, alleen niet als zodanig herkend.

Daarnaast: het piloot-pad liep sinds Fase A dag 5 volledig buiten de financiele governance.
Dat pad draait in productie via `packs.py:337`.

## 2. Zes aannames gemeten, twee sneuvelden

| Aanname | Uitkomst |
| --- | --- |
| `asyncio.wait_for` onderbreekt een LLM-aanroep echt | **Waar** -- `LLMService.generate` is puur async, geen executor of thread in de hele llm-map. De timeout is geen theater |
| `max_steps` is vandaag onbereikbaar | **Onwaar, en dit veranderde het plan.** Ik dacht dat een step pas bestaat bij iteratie; de tool-call-lus in `act()` is die iteratie al |
| De afrekening verandert bij gebruik van de manifestwaarde | **Nee** -- alle 135 manifesten hebben `prana_cost_limit: 100`. Numeriek een no-op, dus veilig |
| `_execute_task` is gedekt in de blokkerende gate | **Nee** -- alleen in `tests/e2e/`. Daarom had de DB-afhankelijkheid van `PranaGuard` daar nooit gebeten |
| De prana-check is zonder meer toe te voegen | **Onwaar** -- 114 seconden voor 4 tests. Zie par. 4 |
| Er is een bestaande limiet-abstractie om te hergebruiken | **Nee** voor per-invocatie limieten; wel voor de onderdelen (`SkillBudget`, `PranaGuard`, `wait_for`). Alleen de compositie is nieuw |

## 3. Ontwerpkeuzes die ik zou verdedigen

**De teller naast `_get_llm_service()` in plaats van op de aanroepplekken.** Een teller die
per call-site leeft, telt niet meer zodra iemand een pad toevoegt -- en dat is precies hoe
het piloot-pad de governance kon omzeilen. Nu komt wie een LLM-pad toevoegt de teller tegen.

**Afkappen meldt zich.** Door de interactie met `success = not errors` (BE-AGT-039 F3)
rapporteert een afgekapte reeks geen succes. Dat is bewust: acht van twintig acties doen en
"gelukt" melden is AUDIT-009 in het klein.

**De guard heeft een vangnet tegen hernoemen.** Zonder
`test_budget_helper_still_exists` zou een rename van `_run_within_budget` de AST-scan voor
iedereen laten slagen: de marker komt dan nergens meer voor, maar wordt ook nergens meer
gezocht. Dat is hoe een guard stilletjes waardeloos wordt.

## 4. Het neveneffect dat vooraf was voorzien -- en waarom dat telt

De prana-check op het piloot-pad maakte 25 tests databaseafhankelijk: **114 seconden voor 4
tests**, het OP-18-patroon van dezelfde dag. Dit stond als risico in het goedgekeurde plan
mét de mitigatie, dus het is geen verrassing geweest maar een ingecalculeerde stap.

Opgelost met een autouse-fixture in `tests/unit/als/conftest.py`. Bewust dáár en niet in twee
testbestanden: de volgende ALS-test hoeft het niet opnieuw te ontdekken. Een autouse-fixture
verbergt gedrag, dus de docstring legt uit waarom hij bestaat en wat er zonder gebeurt. Na de
fix: 33 tests in 2,5 seconden.

## 5. Bevindingen tijdens de review

**F-1 (opgelost, en het soort fout dat ik vandaag vaker maakte).** Mijn eigen
`test_more_llm_calls_than_budget_aborts` was vacuum: hij toetste of een attribuut *bestond*
(`0 is not None`) en riep de mock rechtstreeks aan, dus buiten de teller om. Groen zonder
iets te bewijzen. Herschreven naar `pytest.raises(SkillBudgetExceeded)`, plus een tweede test
op de reset per invocatie -- zonder die reset loopt een langlevende agent na vijf taken vast
op zijn eigen budget.

**F-2 (opgelost tijdens uitvoering).** In een rode test schreef ik
`mock.assert_awaited(), ("melding")` -- een tuple, geen assertie, met de melding als dode
tekst. Pyright meldde het als "Expression value is unused".

**F-3 (opgelost).** In een comment typte ik guillemets in plaats van een `#`-comment:
ongeldige syntax en non-ASCII in één. Direct gecorrigeerd.

**F-4 (meegenomen).** `specialist_base.py` bevatte een em-dash (U+2014) in een logregel --
een NOOIT-lijst-schending in het bestand dat ik toch aanraakte. Eén teken, weg.

**F-5 (geen actie).** De 60s-timeout omvat de tot 3 interne retries met backoff van
`generate`. Dat is bewust -- het budget is de totale grens van de skill, niet die van een
enkele poging -- maar het staat in de feature-doc zodat het geen verrassing wordt wanneer een
trage provider de limiet raakt.

## 6. Compliance-controle

| Regel | Status |
| --- | --- |
| Rode test vóór de fix, eigen commit | OK -- `e36aa531`, 6 failed / 1 passed |
| Mutatie-getest | OK -- drie limieten los gesloopt, elk exact een test rood; guard in beide richtingen |
| ASCII-only | OK -- `specialist_base.py` gecontroleerd: 0 non-ASCII |
| Impact-analyse vóór de eerste wijziging | OK -- in het goedgekeurde plan, inclusief het DB-risico |
| Bevinding zonder directe fix heeft een afdwingende test | OK -- de geen-voortgang-detector is uitgesteld met reden; de guard dekt het aansluitingsrisico |
| Bestaande invarianten intact | OK -- evaluatieset 21/21, 1505 gerichte tests groen |

## 7. Conclusie

**APPROVED**, met één openstaand punt: de dubbele reviewer-GO uit Gate 2 is niet gehaald
omdat die agents deze sessie niet beschikbaar zijn. De wijziging is te groot voor de
small-fix-uitzondering, dus dat hoort alsnog te gebeuren.

Inhoudelijk staat de wijziging: een echt weglooppad is dicht, het piloot-pad valt niet langer
buiten de governance, en de vier gedeclareerde limieten doen voor het eerst iets. Wat
bewust niet is gebouwd -- de geen-voortgang-detector -- staat met reden vermeld in plaats van
stilzwijgend overgeslagen.
