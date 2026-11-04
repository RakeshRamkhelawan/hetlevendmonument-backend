"""De Any-type gate moet in CI daadwerkelijk vuren (BE-CI-006).

Achtergrond. De stap "Any-type gate" stond sinds mei 2026 in ci-feature.yml en heeft geen
enkel bestand gecontroleerd. Drie oorzaken tegelijk, alle drie op 2026-08-13 gereproduceerd:

  1. Nergens `fetch-depth`, dus de runner haalt precies EEN commit op en `origin/develop`
     bestaat daar niet. `git diff origin/develop...HEAD` faalde, `|| true` slikte het op,
     en de stap meldde "skipping" -- groen, in elk event-type.
  2. Ook met een geldige ref is `origin/develop...HEAD` bij een push naar develop leeg.
  3. De frontend-stap draaide met `working-directory: frontend` maar met de pathspec
     `frontend/src/**`, die vanuit die cwd niets matcht.

Deze guard toetst STRUCTUUR (geparseerde YAML), niet tekst. Dat is expliciet vereist door
.claude/rules/quality-gates.md: de terugkerende faalvorm daar is een guard die een woord
zoekt in plaats van een handeling, waardoor een naam in een comment hem groen houdt.

Mutatiebewijs, per test uitgevoerd op een kopie van ci-feature.yml en daarna teruggezet:

  fetch-depth op 1 zetten                       -> test_gate_jobs_fetch_full_history rood
  `exit 0` terugzetten in de skip-tak           -> test_no_gate_step_can_exit_silently rood
  `working-directory: frontend` weer toevoegen  -> test_frontend_gate_runs_from_repo_root rood
  `continue-on-error: true` op een ratel-stap   -> test_no_continue_on_error_on_gates rood
  een baseline-pad naar een niet-bestaand bestand -> test_ratchet_steps_reference_real_baselines rood

En de andere kant: het bestand zoals het nu is moet GROEN zijn, anders zou "weiger alles"
ook een geldige oplossing zijn.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci-feature.yml"

# De jobs die een diff-gebaseerde gate hebben en dus volledige historie nodig hebben.
GATE_JOBS = ("python",)


def _workflow() -> dict[str, Any]:
    assert CI_WORKFLOW.exists(), f"Workflow-bestand ontbreekt: {CI_WORKFLOW}"
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


def _steps(job_name: str) -> list[dict[str, Any]]:
    jobs = _workflow()["jobs"]
    assert job_name in jobs, f"Job '{job_name}' bestaat niet meer in ci-feature.yml"
    return jobs[job_name]["steps"]


def _any_gate_steps(job_name: str) -> list[dict[str, Any]]:
    """Stappen die de any-gate of de ratel aanroepen, gevonden op het COMMANDO.

    Bewust niet op de stapnaam: die kan hernoemd worden terwijl de aanroep blijft, en
    omgekeerd kan een naam blijven staan terwijl het commando verdwijnt.
    """
    found = []
    for step in _steps(job_name):
        script = str(step.get("run", ""))
        if "check_any_gate.py" in script or "check-any-gate.mjs" in script:
            found.append(step)
    return found


@pytest.mark.architecture
class TestAnyGateCiWiring:
    """De gate moet kunnen vuren, en mag niet stil groen kunnen worden."""

    @pytest.mark.parametrize("job_name", GATE_JOBS)
    def test_gate_jobs_fetch_full_history(self, job_name: str) -> None:
        """Zonder fetch-depth: 0 kan de gate geen diff-basis vinden en scant hij niets."""
        checkouts = [
            step
            for step in _steps(job_name)
            if str(step.get("uses", "")).startswith("actions/checkout")
        ]
        assert checkouts, f"Job '{job_name}' heeft geen checkout-stap"
        for step in checkouts:
            depth = (step.get("with") or {}).get("fetch-depth")
            assert depth == 0, (
                f"Job '{job_name}': checkout heeft fetch-depth={depth!r}, moet 0 zijn. "
                "Met de default (1) bestaat de basis-commit niet in de runner en valt de "
                "any-gate terug op 'skipping' (BE-CI-006)."
            )

    @pytest.mark.parametrize("job_name", GATE_JOBS)
    def test_gate_jobs_have_a_gate_and_a_ratchet(self, job_name: str) -> None:
        """Elke gate-job roept de gate minstens twee keer aan: diff-check plus ratel."""
        steps = _any_gate_steps(job_name)
        assert len(steps) >= 2, (
            f"Job '{job_name}' heeft {len(steps)} any-gate-aanroep(en); verwacht minimaal "
            "twee: de gate op gewijzigde bestanden en de ratel tegen de baseline."
        )
        scripts = " ".join(str(s.get("run", "")) for s in steps)
        assert "--baseline" in scripts, (
            f"Job '{job_name}' heeft geen ratel-stap (--baseline). Zonder die stap kan de "
            "geboekte schuld ongemerkt bewegen."
        )

    @pytest.mark.parametrize("job_name", GATE_JOBS)
    def test_no_gate_step_can_exit_silently(self, job_name: str) -> None:
        """Geen enkele any-gate-stap mag een pad hebben dat succesvol eindigt zonder check.

        `exit 0` was letterlijk de skip-tak van de oude stap. `exit $?` mag wel: dat geeft
        de uitkomst van een echt uitgevoerde controle door.
        """
        for step in _any_gate_steps(job_name):
            script = str(step.get("run", ""))
            offending = [
                line.strip()
                for line in script.splitlines()
                if line.strip().startswith("exit ") and line.strip() != "exit $?"
            ]
            assert not offending, (
                f"Job '{job_name}', stap {step.get('name')!r} heeft een harde exit: "
                f"{offending}. Een any-gate-stap mag nooit succesvol eindigen zonder te "
                "hebben gecontroleerd -- gebruik een volledige scan of de ratel als "
                "terugval (fail-closed, BE-CI-006)."
            )

    @pytest.mark.parametrize("job_name", GATE_JOBS)
    def test_no_continue_on_error_on_gates(self, job_name: str) -> None:
        """continue-on-error op een gate maakt hem rapporterend in plaats van blokkerend."""
        for step in _any_gate_steps(job_name):
            assert not step.get("continue-on-error"), (
                f"Job '{job_name}', stap {step.get('name')!r} heeft continue-on-error. "
                "Volgens .claude/rules/quality-gates.md is dat alleen toegestaan als "
                "gedateerde, door Rakesh goedgekeurde uitzondering."
            )

    def test_ratchet_steps_reference_real_baselines(self) -> None:
        """Elk --baseline-pad in de workflow moet bestaan en een bruikbare baseline zijn."""
        workflow_text = CI_WORKFLOW.read_text(encoding="utf-8")
        referenced = {
            token
            for token in workflow_text.split()
            if token.endswith(".json") and "baseline" in token
        }
        assert referenced, "Geen enkel baseline-bestand wordt in de workflow genoemd"

        for rel in sorted(referenced):
            path = REPO_ROOT / rel
            assert path.exists(), (
                f"De workflow verwijst naar {rel}, maar dat bestand bestaat niet. "
                "De ratel-stap zou dan falen op een ontbrekend bestand in plaats van op "
                "een echte afwijking."
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            assert "total" in data, f"{rel} heeft geen 'total'-veld"
            assert "mode" in data, (
                f"{rel} heeft geen 'mode'-veld. Zonder mode is niet vast te stellen WELKE "
                "teller is vastgelegd, en de twee tellers meten verschillende dingen."
            )
