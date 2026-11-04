"""De nachtelijke CI-run moet `develop` meten, niet de default branch.

**Waarom dit bestaat.** GitHub's `schedule`-trigger vuurt altijd op de DEFAULT branch. Gemeten
2026-08-11: 27 van de 27 geplande runs draaiden op `main`, en `main` liep op dat moment 421
commits achter `develop`. De nachtelijke run van 2026-08-11 meldde daardoor acht errors waarvan
er zes op `develop` niet bestonden -- onder andere 66 mypy-fouten die het gevolg waren van de
oude, ongepinde mypy-stap op `main`, en een integratiestap die omviel omdat `main` de
`5435:5432`-poortmapping mist. Dat kostte een halve dag triage van niet-bestaande problemen.

De oplossing is de checkout expliciet naar `develop` laten wijzen wanneer het event `schedule`
is, en anders het standaardgedrag houden (leeg = de ref die het event aanleverde, dus ook de
merge-ref bij een pull_request).

**Waarom een guard erbij hoort.** Dit moet in ELKE job staan. Een job die de `ref` mist meet
stil weer `main`, en dan is de nachtelijke run half betrouwbaar -- wat erger is dan helemaal
niet betrouwbaar, omdat niemand meer weet welke helft.

**Waarom dit STRUCTUUR toetst.** De YAML wordt geparseerd en er wordt per job naar de
`actions/checkout`-stap en zijn `with.ref` gekeken. Een variant die naar de string `develop` in
het bestand zoekt is groen zodra dat woord ergens in een comment of in een branch-filter staat
-- en `on.push.branches` bevat het al.

**Mutatietest (uitgevoerd, beide richtingen).**
- De `ref` uit een van de zes checkout-stappen halen maakt deze test ROOD en noemt die job.
- Met de `ref` in alle zes is hij groen, en een job zonder checkout-stap (zoals een job die
  alleen een reusable workflow aanroept) wordt niet ten onrechte geeist.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci-feature.yml"

#: De twee delen die de expressie MOET bevatten. Los getoetst, zodat een `ref` die wel
#: `develop` noemt maar niet aan het schedule-event hangt (of omgekeerd) alsnog rood is.
_VEREIST_EVENT = "github.event_name == 'schedule'"
_VEREISTE_BRANCH = "develop"


def _checkout_stappen() -> list[tuple[str, dict]]:
    """Elke `actions/checkout`-stap, met de naam van zijn job."""
    import yaml

    parsed = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")) or {}
    gevonden: list[tuple[str, dict]] = []
    for jobnaam, job in (parsed.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for stap in job.get("steps") or []:
            if not isinstance(stap, dict):
                continue
            if str(stap.get("uses", "")).startswith("actions/checkout"):
                gevonden.append((jobnaam, stap))
    return gevonden


def test_every_checkout_pins_develop_on_a_scheduled_run() -> None:
    """Elke checkout-stap MOET op een schedule-run naar `develop` wijzen."""
    stappen = _checkout_stappen()
    tekort: list[str] = []
    for jobnaam, stap in stappen:
        ref = str(((stap.get("with") or {}).get("ref")) or "")
        if _VEREIST_EVENT not in ref or _VEREISTE_BRANCH not in ref:
            tekort.append(f"{jobnaam} (ref={ref!r})")

    assert not tekort, (
        "Deze jobs checken op een geplande run niet expliciet `develop` uit en meten dus de "
        f"default branch: {tekort}.\n"
        "GitHub's schedule-trigger draait ALTIJD op de default branch. Gemeten 2026-08-11: "
        "27/27 geplande runs op `main`, terwijl `main` 421 commits achterliep -- zes van de acht "
        "gemelde errors bestonden niet op develop.\n"
        "Voeg toe:  with:\\n    ref: ${{ github.event_name == 'schedule' && 'develop' || '' }}"
    )


def test_the_scan_actually_finds_the_checkout_steps() -> None:
    """Vangnet tegen een guard die niets meet.

    Verandert de workflow van vorm (andere action, andere nesting), dan vindt de test hierboven
    nul stappen en is hij stil groen. Deze test eist dat er er meerdere gevonden worden EN dat
    elke job die stappen heeft er een checkout in heeft -- want juist een job zonder checkout-ref
    is het gat dat we dichthouden.
    """
    import yaml

    stappen = _checkout_stappen()
    assert len(stappen) >= 2, (
        f"Slechts {len(stappen)} checkout-stap(pen) gevonden in {WORKFLOW.name}. De scan meet "
        "dan (bijna) niets en de guard hierboven is vacuum."
    )

    parsed = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")) or {}
    jobs_met_stappen = {
        naam
        for naam, job in (parsed.get("jobs") or {}).items()
        if isinstance(job, dict) and job.get("steps")
    }
    jobs_met_checkout = {jobnaam for jobnaam, _ in stappen}
    zonder = sorted(jobs_met_stappen - jobs_met_checkout)
    assert not zonder, (
        f"Deze jobs hebben stappen maar geen actions/checkout: {zonder}. Controleer of dat klopt; "
        "zo ja, dan hoort deze guard een gedateerde uitzondering te krijgen in plaats van een "
        "stille blinde vlek."
    )
