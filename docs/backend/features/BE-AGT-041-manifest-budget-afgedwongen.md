# BE-AGT-041 -- Het manifest-budget wordt echt afgedwongen

| Veld | Waarde |
| --- | --- |
| Feature-ID | BE-AGT-041 |
| Datum | 2026-08-01 |
| ADR | ADR-036 D10 stap 5 (loop-engineering) |
| Sprint | ADR-036 Fase B / Fase 2 / dag 1 |
| Omvang | 1 helper + 2 aansluitingen + 1 begrenzing; 8 unit-tests, 3 arch-tests |

---

## 1. Probleem

`SkillBudget` (`als/agents/skill_manifest.py`) parseert `max_steps`, `max_llm_calls`,
`timeout_seconds` en `prana_cost_limit`. Die velden kwamen alleen terug in `to_dict()`. Alle
**135 manifesten declareren identieke waarden** (8 / 5 / 60 / 100) -- 135 kopieen van
boilerplate die niets deed.

### 1.1 Het weglooppad dat open stond

Niet theoretisch. `_parse_tool_calls()` gebruikt `finditer` **zonder limiet** op het
LLM-antwoord, en `act()` voerde elke gevonden directive sequentieel uit met 30s timeout per
tool. Een antwoord met 50 `TOOL_CALL`-regels betekende 50 uitvoeringen en tot ~25 minuten
werk, per invocatie. `max_steps=8` past precies op dat gat.

### 1.2 Het piloot-pad omzeilde de bestaande governance

`_execute_task()` deed altijd al `PranaGuard.check_budget()` vooraf en `charge_prana()`
achteraf. Maar `execute_with_manifest_prompt()` -- het pad dat `packs.py:337` in productie
gebruikt -- roept `_execute_task` niet aan. Dus: geen budgetcheck, geen afrekening, geen
tijdslimiet.

Dat was de onbedoelde prijs van de kortere weg uit Fase A dag 5 (K1 optie A, om `orient()`
te omzeilen). Een tweede pad naast een bestaand pad loopt uiteen zolang niets de gelijkenis
afdwingt -- daarom hoort bij deze fix een guard en niet alleen een reparatie.

### 1.3 De enige bestaande timeout sprak het manifest tegen

`_run_single_step()` (`packs.py:265`) wrapt de stap in
`asyncio.wait_for(timeout=step.sla_seconds)` = **600s** voor de piloot, terwijl het manifest
**60s** declareert. Buiten een pack gold er helemaal geen timeout.

## 2. Oplossing

Eén afdwingpunt, `BaseSpecialistAgent._run_within_budget()`, gebruikt door **beide** paden.
Het handhaaft:

| Limiet | Waar | Bij overschrijding |
| --- | --- | --- |
| `timeout_seconds` | `asyncio.wait_for` om het hele werk | `ExecutionResult(success=False)` met "timeout" en de waarde in de melding |
| `max_llm_calls` | `_count_llm_call()`, naast `_get_llm_service()` | `SkillBudgetExceeded` met de limiet in de melding |
| `max_steps` | `act()`, op het aantal tool-calls | afkappen **plus** een expliciete regel in `errors` |
| `prana_cost_limit` | afrekening bij succes | -- (vervangt de hardcoded `100`) |

Plus de tenant-prana-check via de bestaande `PranaGuard.check_budget()`, nu ook op het
piloot-pad.

**Hergebruikt, niet opnieuw gebouwd:** `SkillBudget.from_dict()`, `PranaGuard`,
`asyncio.wait_for` (het patroon uit `packs.py:265` en `tool_broker/health.py:282`).

### 2.1 Drie ontwerpkeuzes met hun reden

**De manifest-timeout is de binnenste grens, de pack-SLA de buitenste.** De eigen limiet
beschermt de skill, de SLA beschermt de pack. Beide blijven gelden; de strakkere zit binnen
en wint automatisch. Er is niets weggehaald.

**De LLM-teller zit naast `_get_llm_service()`, niet op de aanroepplekken.** Wie een nieuw
LLM-pad toevoegt komt hem daar tegen. Een teller verspreid over call-sites rot weg zodra
iemand een pad toevoegt -- precies het gat dat deze fase moet dichten.

**Afkappen wordt gemeld, niet verzwegen.** Bij meer dan `max_steps` tool-calls komt er een
regel in `errors`, en omdat `success = not errors` (BE-AGT-039 F3) rapporteert de stap geen
succes. Acht van twintig acties uitvoeren en succes melden is precies wat AUDIT-009 afkeurde.

## 3. Wat bewust NIET is gebouwd

De **geen-voortgang-detector** die D10 stap 5 ook noemt. Die is alleen zinvol en alleen
testbaar bij iteratie over meerdere OODA-rondes; die iteratie bestaat nog niet. Hem nu bouwen
levert een component op die getest is en niets aanroept -- het vierde geval van het patroon
dat deze fase juist moet opruimen (tools gedeclareerd niet uitvoerbaar, budget geparseerd
niet gehandhaafd, Council-poort gebouwd niet aangeroepen). Hij komt met de lus.

## 4. Tests

`tests/unit/als/test_skill_budget_enforcement.py` -- 8 tests, 6 rood gecommit in `e36aa531`.
Mutatie-getest: de `max_steps`-begrenzing weghalen, de timeout weghalen, en de afrekening
terugzetten op `100` maken elk exact één test rood.

`tests/architecture/test_skill_execution_paths_are_budgeted.py` -- 3 tests. Een AST-scan
(geen grep: die mist een aanroep over meerdere regels) die elke skill-methode vindt die zelf
de LLM aanroept zonder door de helper te lopen. Inclusief een vangnet dat faalt als de helper
wordt hernoemd -- anders zou een rename de scan stilzwijgend vacuum maken. Beide richtingen
mutatie-getest.

### 4.1 Een vacuum-test die ik zelf schreef

De eerste versie van `test_more_llm_calls_than_budget_aborts` toetste alleen of er een
teller-attribuut *bestond* (`0 is not None` -- altijd waar) en riep de mock rechtstreeks aan,
dus buiten de teller om. Groen zonder iets te bewijzen. Herschreven naar
`pytest.raises(SkillBudgetExceeded)` op de zesde aanroep, plus een tweede test die vastlegt
dat de teller per invocatie reset -- zonder die reset zou een langlevende agent na vijf taken
op zijn eigen budget vastlopen.

## 5. Neveneffect dat vooraf was voorzien

De prana-check op het piloot-pad maakte 25 bestaande tests databaseafhankelijk:
`check_budget()` opent een echte sessie, en zonder database volgt vijf keer retry met
backoff. Gemeten: **114 seconden voor 4 tests**. Dat is exact het defect dat dezelfde dag als
OP-18 is opgeruimd.

Opgelost met een autouse-fixture in `tests/unit/als/conftest.py` die `PranaGuard` stubt. Die
keuze in plaats van twee bestanden patchen: hij dekt ook toekomstige ALS-unittests, zodat de
volgende test het niet opnieuw hoeft te ontdekken. De fixture heeft een naam, dus tests die
op de aanroepen willen asserteren vragen hem gewoon op. Na de fix: 33 tests in 2,5 seconden.

Dit is meteen een eerste, gescopete stap richting het openstaande deel van OP-18 -- een
structurele borging dat unittests geen databaseverbinding openen.

## 6. Trainingssamenvatting

**Flow 1 -- het model vraagt meer tool-calls dan het budget toestaat**

- Actor: ALS-skill met een permissieprofiel
- Voorwaarde: het LLM-antwoord bevat meer `TOOL_CALL`-directives dan `max_steps`
- Actie: `act()` verwerkt het antwoord
- Systeemreactie: alleen de eerste `max_steps` worden uitgevoerd; er komt een regel in
  `errors` die de overschrijding en het aantal benoemt; `success` is False
- Succes: n.v.t.
- Fout: expliciet gemeld, niet stil afgekapt
- Uitzonderingen: geen; de grens komt uit het manifest van de skill zelf

**Flow 2 -- het werk duurt langer dan de gedeclareerde tijd**

- Actor: elke skill
- Voorwaarde: de uitvoering overschrijdt `timeout_seconds` uit het manifest
- Actie: `_run_within_budget()` bewaakt de tijd
- Systeemreactie: het werk wordt afgebroken; de melding bevat "timeout" en de gehanteerde
  waarde
- Succes: n.v.t.
- Fout: onderscheidbaar van een echte storing doordat de limiet in de tekst staat
- Uitzonderingen: de pack-SLA blijft als buitenste grens gelden

**Flow 3 -- de tenant heeft geen prana meer**

- Actor: elke skill, op beide uitvoerpaden
- Voorwaarde: `PranaGuard.check_budget()` weigert
- Actie: een invocatie start
- Systeemreactie: er wordt geen LLM aangeroepen en geen tool uitgevoerd; er komt een
  mislukt `ExecutionResult` met de reden
- Succes: n.v.t.
- Fout: fail-closed
- Uitzonderingen: geen -- sinds deze wijziging geldt dit ook voor het piloot-pad, dat er
  eerder omheen liep

## 7. Gewijzigde bestanden

| Bestand | Wijziging |
| --- | --- |
| `src/core/als/agents/skill_manifest.py` | `SkillBudgetExceeded` toegevoegd, naast `SkillBudget` |
| `src/core/als/agents/specialist_base.py` | budget ingelezen in `__init__`; `_count_llm_call()`; `_run_within_budget()`; `_get_prana_guard()`; `_execute_task()` erdoorheen; `max_steps`-begrenzing in `act()`. Ook: em-dash op de allowed_tools-logregel weg (ASCII-regel) |
| `src/core/als/agents/skills/skillsgaptraining.py` | `execute_with_manifest_prompt()` door de helper |
| `tests/unit/als/conftest.py` | nieuw -- autouse PranaGuard-stub |
| `tests/unit/als/test_skill_budget_enforcement.py` | nieuw -- 8 tests |
| `tests/architecture/test_skill_execution_paths_are_budgeted.py` | nieuw -- 3 tests |
