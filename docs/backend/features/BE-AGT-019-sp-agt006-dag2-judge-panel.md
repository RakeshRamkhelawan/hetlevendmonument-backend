# Backend Feature Specification

## Metadata

- Feature ID: BE-AGT-019
- Feature naam: Multi-model Judge Panel -- Prometheus-eval patroon in CriticAgent
- Status: APPROVED
- Auteur: SP-AGT-006 Dag 2
- Reviewer: doc-reviewer subagent
- Datum: 2026-06-27
- Gerelateerde user story / ticket: SP-AGT-006
- Gerelateerde router / module: src/core/agents/critic_agent.py
- Gerelateerde frontend endpoints: geen
- Gerelateerde database tabellen: agent_critiques (via CritiqueStore)
- Versie: 1.0

---

## Doel en scope

### Doel

Ambigue heuristic+LLM scores in de zone [0.35, 0.75] worden beoordeeld door N=3
onafhankelijke LLM-judges via asyncio.gather(return_exceptions=True). Consensus
vervangt de blended score. Volledig transparant via metadata["judge_panel"].

### In scope

- `SingleJudgeVerdict` dataclass (judge_index, score, issues, suggestions)
- `JudgePanelVerdict` dataclass (consensus, verdicts, outliers_removed, failed_judges, raw_scores)
- Module-level constanten: `_JUDGE_PANEL_LOWER = 0.35`, `_JUDGE_PANEL_UPPER = 0.75`, `_OUTLIER_THRESHOLD = 0.30`
- `CriticAgent._judge_panel_critique()` -- bouwt prompt, roept _run_judge_panel aan
- `CriticAgent._run_judge_panel()` -- asyncio.gather N judges, timeout 15s/judge, asyncio.TimeoutError -> (index, None)
- `CriticAgent._build_judge_panel_verdict()` -- leave-one-out outlier detection, threshold 0.30
- Activatielogica in `critique_task()` als Phase 3 (na heuristic + LLM, alleen als use_llm=True EN score in [0.35, 0.75])
- `metadata["judge_panel"]` opgeslagen in Critique bij succesvolle panel-run
- `heuristic_score` correct gecaptured VOOR LLM-blending in metadata

### Out of scope

- Verschillende LLM-providers per judge (alle judges gebruiken dezelfde _get_llm_client())
- Persistentie van SingleJudgeVerdict als aparte tabelrij
- Config-gestuurde N (momenteel hardcoded N=3)

---

## Build summary

- Nieuw gebouwd:
  - `SingleJudgeVerdict` dataclass
  - `JudgePanelVerdict` dataclass
  - `CriticAgent._judge_panel_critique()` methode
  - `CriticAgent._run_judge_panel()` methode
  - `CriticAgent._build_judge_panel_verdict()` methode
  - `tests/unit/agents/test_critic_agent_judge_panel.py` (8 tests)
- Gewijzigd:
  - `CriticAgent.critique_task()` -- Phase 3 activatielogica toegevoegd
- Verwijderd: geen
- Beinvloede bestaande flows:
  - `critique_task()` -- aanroepende code die een `Critique` verwacht bij score in [0.35, 0.75]
    met use_llm=True krijgt nu een panel-consensus score terug, met `metadata["judge_panel"]`

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
|----|------|------|-------------|-----------------|-------------------|
| BE-AGT-019-A | SingleJudgeVerdict | dataclass | src/core/agents/critic_agent.py | Nieuw | Judge panel resultaat per judge |
| BE-AGT-019-B | JudgePanelVerdict | dataclass | src/core/agents/critic_agent.py | Nieuw | Geaggregeerd panel-oordeel |
| BE-AGT-019-C | _judge_panel_critique() | methode | src/core/agents/critic_agent.py | Nieuw | Prompt + panel orchestratie |
| BE-AGT-019-D | _run_judge_panel() | methode | src/core/agents/critic_agent.py | Nieuw | asyncio.gather N judges |
| BE-AGT-019-E | _build_judge_panel_verdict() | methode | src/core/agents/critic_agent.py | Nieuw | Leave-one-out outlier detection |
| BE-AGT-019-F | critique_task() Phase 3 | methode (wijziging) | src/core/agents/critic_agent.py | Wijziging | Panel-activatie in hoofdpijplijn |
| BE-AGT-019-G | test_critic_agent_judge_panel.py | testbestand | tests/unit/agents/test_critic_agent_judge_panel.py | Nieuw | TDD-dekking judge panel |

---

## Detaildocumentatie per artefact

---

### [BE-AGT-019-A] SingleJudgeVerdict

**Type:** dataclass (Python stdlib `dataclasses`)
**Locatie:** `src/core/agents/critic_agent.py`, na imports, voor `JudgePanelVerdict`

**Doel:** Resultaatobject dat het oordeel van een individuele judge vastlegt.

**Technische beschrijving:**

```python
@dataclass
class SingleJudgeVerdict:
    judge_index: int
    score: float
    issues: list[str]
    suggestions: list[str]
```

**Acceptatiecriteria:**
- Alle vier velden verplicht (geen defaults)
- `score` is een float in het bereik [0.0, 1.0]

---

### [BE-AGT-019-B] JudgePanelVerdict

**Type:** dataclass (Python stdlib `dataclasses`)
**Locatie:** `src/core/agents/critic_agent.py`, na `SingleJudgeVerdict`

**Doel:** Geaggregeerd eindoordeel van het volledige panel na outlier-filtering.

**Technische beschrijving:**

```python
@dataclass
class JudgePanelVerdict:
    consensus: float
    verdicts: list[SingleJudgeVerdict]
    outliers_removed: int
    failed_judges: int
    raw_scores: list[float]
```

**Acceptatiecriteria:**
- `consensus` is het gemiddelde van de overgebleven scores na outlier-filtering
- `outliers_removed` is 0 of 1 (voor N=3)
- `failed_judges` telt judges met timeout of parse-fout
- `raw_scores` bevat de onbewerkte scores van alle succesvolle judges (voor traceerbaarheid)

---

### [BE-AGT-019-C] CriticAgent._judge_panel_critique()

**Type:** methode (nieuw, async)
**Locatie:** `src/core/agents/critic_agent.py`, klasse `CriticAgent`

**Functionele beschrijving:**
Bouwt de judge-prompt, roept `_run_judge_panel` aan met `timeout_per_judge=15.0`, en
roept daarna `_build_judge_panel_verdict` aan. Retourneert `None` als alle judges falen.

**Technische beschrijving:**

- Prompt is identiek voor alle judges; output gecapped op 2000 tekens
- Bij volledig falen (geen geldige scores): retourneert `None`
- Logt `logger.warning` bij partial failure (1 of 2 judges falen)
- Logt `logger.error` bij volledig falen

**Acceptatiecriteria:**
- Retourneert `JudgePanelVerdict` als minimaal 2 judges slagen
- Retourneert `None` als minder dan 2 judges slagen
- Prompt-lengte boven 2000 chars: output gecapped, geen exception

**Trainingssamenvatting:**
- Actor: CriticAgent (intern, aangeroepen vanuit critique_task Phase 3)
- Voorwaarde: use_llm=True, score in [0.35, 0.75]
- Actie: await _judge_panel_critique(agent_name, task_id, result, score)
- Systeemverwerking: bouwt prompt, spawnt N judges, aggregeert resultaat
- Succesrespons: JudgePanelVerdict met consensus score
- Foutrespons: None bij volledig falen
- Uitzonderingen: partial failure -> consensus van beschikbare judges

---

### [BE-AGT-019-D] CriticAgent._run_judge_panel()

**Type:** methode (nieuw, async)
**Locatie:** `src/core/agents/critic_agent.py`, klasse `CriticAgent`

**Technische beschrijving:**

- `asyncio.gather(*tasks, return_exceptions=True)` -- nooit propagate
- `asyncio.TimeoutError` -> `(index, None)` met `logger.warning`
- Alle andere exceptions -> `(index, None)` met `logger.error` en `exc_info=True`
- Elke task is een `asyncio.wait_for(_single_judge_call(...), timeout=timeout_per_judge)`

**Parse-error pad (BE-AGT-019-minor-3):**

Een parse-fout treedt op als `_single_judge_call()` de LLM-response niet kan parsen
tot een geldige float score (bijv. de LLM antwoordt met proza i.p.v. `{"score": 0.75}`).

Afhandelingsstrategie:

1. `_single_judge_call()` probeert de LLM-response te parsen; bij mislukking gooit het een exception.
2. `_run_judge_panel()` vangt dit op via het algemene `except Exception` blok (na `asyncio.TimeoutError`).
3. Resultaat voor die judge: `(index, None)` -- de judge telt als `failed_judge`.
4. `logger.error(..., exc_info=True)` wordt gelogd (volledig stacktrace, niet alleen een string).
5. Als er na filtering < 2 geldige scores overblijven, retourneert `_judge_panel_critique()` `None`
   en blijft de score van Phase 2 ongewijzigd.

**Onderscheid timeout vs. parse-fout in `failed_judges`:** beide soorten fouten tellen als
`failed_judges` in `JudgePanelVerdict`. De `metadata["judge_panel"]` onderscheidt geen
parse-fouten van timeouts (beide worden als `failed_judges: N` opgeslagen).
Fijnere logging per faaltype is een toekomstig sprint-item.

**Acceptatiecriteria:**
- Geen enkele exception propageert naar de aanroeper
- Elk faalpad retourneert `(index, None)` als tupel
- `return_exceptions=True` op asyncio.gather (nooit False)
- Parse-fout telt als `failed_judge`, niet als exception in de aanroepende pijplijn

---

### [BE-AGT-019-E] CriticAgent._build_judge_panel_verdict()

**Type:** methode (nieuw)
**Locatie:** `src/core/agents/critic_agent.py`, klasse `CriticAgent`

**Functionele beschrijving:**
Leave-one-out outlier detection: voor elke score wordt de afwijking van het gemiddelde
van de overige N-1 scores berekend. Als `max_deviation > 0.30`: verwijder die score,
`outliers_removed=1`. Minimaal 2 scores vereist voor consensus.

**Motivatie leave-one-out i.p.v. 2-sigma:**
Voor N=3 is de maximale z-score wiskundig ~1.15, wat altijd kleiner is dan 2.
Een 2-sigma grens zou nooit triggeren voor N=3. Leave-one-out met een absolute
drempel van 0.30 is het correcte patroon voor kleine panels.

**Drempelkeuze 0.30 (BE-AGT-019-minor-2):**

De constante `_OUTLIER_THRESHOLD = 0.30` is gekozen op basis van drie overwegingen:

1. **Score-bereik:** het panel wordt alleen geactiveerd voor scores in [0.35, 0.75] (bereik = 0.40).
   Een outlier moet substantieel afwijken -- minimaal 75% van het activatiebereik.
   Drempel 0.30 / bereik 0.40 = 75% is een conservatieve keuze.

2. **Panelgrootte N=3:** voor N=3 is een afwijking kleiner dan 0.30 eerder ruis dan een echte outlier.
   Een te lage drempel (bijv. 0.10) zou valide score-variatie verwijderen; een te hoge drempel
   (bijv. 0.50) zou echte extremen nooit detecteren.

3. **Kerngebruiksscenario:** het panel is bedoeld om extreme afwijkers te detecteren
   (bijv. 0.10 tegenover 0.60/0.62), niet om subtiele variatie te egaliseren.
   Een drempel van 0.30 filtert alleen overduidelijke uitschieters.

De constante is module-level en kan in een toekomstige sprint config-gestuurd worden gemaakt
via `critic_agent.yaml`. Huidige scope: hardcoded.

**Technische beschrijving:**

```
Voor elke score s_i in scores:
    overige = [s_j for j != i]
    mean_overige = mean(overige)
    afwijking = abs(s_i - mean_overige)
    als afwijking > 0.30: markeer als outlier

Als een outlier gevonden: verwijder die score, outliers_removed=1.
Consensus = mean(resterende scores).
```

**Acceptatiecriteria:**
- Scores [0.60, 0.62, 0.10]: outliers_removed=1, outlier=0.10, consensus ~0.61
- Scores [0.60, 0.62, 0.58]: outliers_removed=0, consensus ~0.60
- Bij minder dan 2 scores na filtering: retourneert None (aanroeper handelt dit af)

---

### [BE-AGT-019-F] critique_task() Phase 3

**Type:** methode (wijziging van bestaande async methode)
**Locatie:** `src/core/agents/critic_agent.py`, klasse `CriticAgent`

**Technische beschrijving:**

Phase 3 wordt toegevoegd na Phase 1 (heuristic) en Phase 2 (LLM-blending):

```python
# heuristic_score gecaptured na Phase 1, voor LLM-blending
heuristic_score = heuristic_result.score
metadata["heuristic_score"] = heuristic_score

# Phase 2: LLM-blending (bestaand)
# ...
score = blended_score  # score na Phase 2

# Phase 3: Judge panel (nieuw)
if use_llm and _JUDGE_PANEL_LOWER <= score <= _JUDGE_PANEL_UPPER:
    panel_verdict = await self._judge_panel_critique(
        agent_name, task_id, result, score
    )
    if panel_verdict is not None:
        score = panel_verdict.consensus
        metadata["judge_panel"] = {
            "consensus": panel_verdict.consensus,
            "outliers_removed": panel_verdict.outliers_removed,
            "failed_judges": panel_verdict.failed_judges,
            "raw_scores": panel_verdict.raw_scores,
        }
```

**Business rules:**
- `heuristic_score` gecaptured VOOR LLM-blending (niet de blended score)
- `metadata["heuristic_score"] = heuristic_score` (traceerbaarheid van originele heuristic)
- Panel alleen als `use_llm=True AND _JUDGE_PANEL_LOWER <= score <= _JUDGE_PANEL_UPPER`
- `panel_verdict is None` -> score ongewijzigd, geen `judge_panel` in metadata

**Activatiecriterium (exact):**

    use_llm=True AND _JUDGE_PANEL_LOWER <= score <= _JUDGE_PANEL_UPPER
    (score = score na Phase 2 LLM-blending)

**use_llm=False conditie (BE-AGT-019-minor-1):**

Als `use_llm=False` wordt meegegeven aan `critique_task()`:
- Phase 2 (LLM-blending) wordt overgeslagen -- score blijft de pure heuristic score.
- Phase 3 (judge panel) wordt nooit aangeroepen, ongeacht de score-waarde.
- De `Critique` bevat geen `metadata["judge_panel"]` key.
- `metadata["heuristic_score"]` is ook niet aanwezig (Phase 2 en 3 beide overgeslagen).

Dit is het verwachte gedrag voor interne agents die deterministische critiques vereisen
(unit-tests, cron-jobs, schema-validatie-pijplijnen). De caller geeft expliciet aan
dat LLM-escalatie niet gewenst is -- het panel wordt dus nooit geactiveerd.

**Acceptatiecriteria:**
- Panel geactiveerd: `metadata["judge_panel"]["consensus"]` aanwezig, score == consensus
- Panel niet geactiveerd bij score < 0.35: metadata heeft geen "judge_panel" key
- Panel niet geactiveerd bij score > 0.75: metadata heeft geen "judge_panel" key
- Panel niet geactiveerd bij use_llm=False: metadata heeft geen "judge_panel" key
- Alle judges timeout: score ongewijzigd, geen judge_panel in metadata
- 1 van 3 judges timeout: failed_judges=1, consensus van 2 succesvolle judges

**Trainingssamenvatting:**
- Actor: WorkflowService die critique_task aanroept met use_llm=True
- Voorwaarde: heuristic + LLM al gedraaid, score in [0.35, 0.75]
- Actie: `await critic_agent.critique_task(agent_name, task_id, result, use_llm=True)`
- Systeemverwerking: Phase 3 spawnt N=3 LLM-judges via asyncio.gather; consensus vervangt score
- Succesrespons: Critique met consensus score en metadata["judge_panel"]
- Foutrespons (panel volledig timeout): Critique met oorspronkelijke blended score, geen judge_panel
- Uitzonderingen: partial failure (1 judge timeout) -> consensus van 2 succesvolle judges

---

## Acceptatiecriteria (sprint-totaal)

- Panel geactiveerd bij score in [0.35, 0.75] en use_llm=True: metadata["judge_panel"]["consensus"] aanwezig
- Panel niet geactiveerd bij score < 0.35: geen "judge_panel" key in metadata
- Panel niet geactiveerd bij score > 0.75: geen "judge_panel" key in metadata
- Outlier 0.10 uit [0.60, 0.62, 0.10]: outliers_removed=1, consensus ~0.61
- Geen outlier uit [0.60, 0.62, 0.58]: outliers_removed=0, consensus ~0.60
- Alle judges timeout: score ongewijzigd, geen judge_panel in metadata
- 1 van 3 judges timeout: failed_judges=1, consensus van 2 succesvolle judges
- `metadata["heuristic_score"]` aanwezig (gecaptured voor LLM-blending)
- 8/8 unit tests groen
- `python -m pyright` 0 nieuwe errors
- `ruff check src/core/agents/critic_agent.py` 0 violations

---

## Trainingssamenvatting (hoofdflow)

- **Actor:** Externe service (bijv. WorkflowService) die een agent-taak heeft uitgevoerd
- **Voorwaarde:** CriticAgent geinitialiseerd voor tenant_id; ExecutionResult beschikbaar; score in [0.35, 0.75]
- **Actie:** `await critic_agent.critique_task(agent_name, task_id, result, use_llm=True)`
- **Systeemverwerking:**
  1. Phase 1: HeuristicScorer -> heuristic_score gecaptured
  2. Phase 2: LLM-blending -> blended score
  3. Phase 3 (conditioneel): Judge panel spawnt N=3 judges via asyncio.gather
     3a. Panel slaagt: Critique met consensus score en metadata["judge_panel"]
     3b. Panel faalt volledig: Critique met blended score, geen judge_panel
- **Succesrespons:** Critique met score 0.0-1.0, gevuld issues en suggestions, metadata["judge_panel"]
- **Foutrespons (panel volledig timeout):** Critique met blended score, geen judge_panel in metadata
- **Uitzonderingen:** partial failure -> consensus van succesvolle judges

---

## Open aannames

- Alle judges gebruiken dezelfde LLM provider (diversiteit via prompt is enige bron van variatie)
- N=3 hardcoded; config-gestuurde N is toekomstig sprint-item

## Open vragen

- Geen blokkerende open vragen

## Risico-overzicht

- Zelfde provider voor alle judges vermindert diversiteit vs. echte Prometheus-eval multi-model setup
- Timeout 15s/judge: bij 3 parallel judges is worst-case latency 15s (allen gelijktijdig timeout)

---

## QA-checks

- [x] Panel-activatiecriterium functioneel getest (happy path)
- [x] Grenswaarden getest (score=0.35 exact, score=0.75 exact, score=0.34, score=0.76)
- [x] Outlier-detectie getest (met en zonder outlier)
- [x] Timeout-gedrag getest (alle judges timeout, partial timeout)
- [x] heuristic_score-capture getest (aanwezig in metadata, is pre-blending waarde)
- [x] Tenant-isolatie: geen wijzigingen aan tenant-isolatielogica
- [x] pyright 0 errors
- [x] ruff 0 violations

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten geinventariseerd
- [x] Alle foutpaden beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Trainingssamenvatting aanwezig
- [x] Open aannames benoemd
- [x] QA-checks uitgevoerd
- [x] Review: APPROVED WITH MINOR GAPS (minors: LLM-diversiteit beperkt, N hardcoded, parse-error pad impliciet)
