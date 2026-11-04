"""De lokale CI-runner MOET elke job uit ci-feature.yml kennen.

**Waarom deze guard bestaat.** GitHub Actions draait sinds 2026-09-12 niet meer: het
abonnement is opgezegd en de runners worden geweigerd. De workflow blijft in de repo
staan als beschrijving van wat er gecontroleerd moet worden, maar de uitvoering ligt bij
`scripts/run_ci_act.ps1` (act, in Docker) en bij de pre-push hook. Zonder deze guard kan
iemand een job aan `ci-feature.yml` toevoegen die vervolgens NERGENS draait -- de
workflow is immers stil, dus niets wordt rood. Dat is precies hoe dit project eerder drie
weken mypy-schuld opliep zonder signaal.

De guard toetst daarom of de `ValidateSet` van de runner exact gelijk is aan de jobs in
de workflow. Hij zegt NIETS over de vraag of een job groen is -- alleen dat de runner hem
kent, en dus of hij draait of met reden gemeld wordt.

**Mutatiebewijs (2026-09-14), beide richtingen:**
  1. Een extra job `nieuwe-job:` in ci-feature.yml -> ROOD ("kent de runner niet").
  2. `'security'` uit de ValidateSet verwijderd -> ROOD ("kent de runner niet meer").
  3. Onaangeroerde boom -> GROEN.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_WORKFLOW = Path(".github/workflows/ci-feature.yml")
_RUNNER = Path("scripts/run_ci_act.ps1")


def _workflow_jobs() -> set[str]:
    data = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    jobs = data.get("jobs") or {}
    assert jobs, f"{_WORKFLOW} bevat geen jobs -- dan meet deze guard niets."
    return set(jobs)


def _runner_jobs() -> set[str]:
    """Leest de ValidateSet van de -Job parameter uit de runner.

    Bewust GEEN losse substring-zoektocht naar jobnamen in het hele bestand: die zou ook
    een naam in een comment of in een foutmelding accepteren, en dan bewaakt de guard
    tekst in plaats van de parameter die de runner echt accepteert.
    """
    bron = _RUNNER.read_text(encoding="utf-8")
    treffer = re.search(r"\[ValidateSet\(([^)]*)\)\]", bron)
    assert treffer, f"Geen ValidateSet gevonden in {_RUNNER} -- guard kan niets toetsen."
    return set(re.findall(r"'([^']+)'", treffer.group(1)))


def test_de_runner_kent_elke_job_uit_de_workflow() -> None:
    """Elke job in ci-feature.yml MOET in de ValidateSet van de runner staan."""
    workflow, runner = _workflow_jobs(), _runner_jobs()
    ontbreekt = workflow - runner
    assert not ontbreekt, (
        f"Deze jobs staan in {_WORKFLOW} maar kent de runner niet: {sorted(ontbreekt)}. "
        f"GitHub Actions draait niet meer, dus zo'n job draait NERGENS en wordt nooit rood. "
        f"Voeg hem toe aan de ValidateSet van {_RUNNER}, en zet hem in de standaardlijst "
        f"of in $buitenAct met de gemeten reden erbij."
    )


def test_de_runner_kent_geen_jobs_die_niet_meer_bestaan() -> None:
    """Een verwijderde job MOET uit de runner -- anders rot de lijst dicht."""
    workflow, runner = _workflow_jobs(), _runner_jobs()
    verdwenen = runner - workflow
    assert not verdwenen, (
        f"Deze jobs kent {_RUNNER} nog wel, maar staan niet meer in {_WORKFLOW}: "
        f"{sorted(verdwenen)}. Verwijder ze uit de ValidateSet."
    )
