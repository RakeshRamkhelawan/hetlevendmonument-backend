"""Elke gedeployde app op de worker-image heeft REDIS_URL nodig (ADR-036 OP-87).

**Hoe dit gevonden is.** Bij het toevoegen van de scheduler-app bleek de staging-worker bij
AANMAAK geen `REDIS_URL` mee te krijgen, en bij UPDATE evenmin. `src/workers/workflow_worker.py`
gooit zonder die variabele een `RuntimeError` bij het IMPORTEREN -- niet bij gebruik, bij importeren.
Omdat het entrypoint dramatiq is, draait er geen bootcheck die dat netjes meldt: de container start,
valt om, en de deploy meldt succes.

**Waarom een guard en niet alleen de fix.** Dit is de derde keer in deze reeks dat iets zich gezond
meldt en niets doet -- eerst een planner die nergens startte, toen een planner die naar een
geheugenwachtrij stuurde, toen een werker die geen enkele wachtrij consumeerde. Het patroon is
telkens dat de FOUT onzichtbaar is. Een guard die de deployconfiguratie leest is de enige plek waar
dit voor een deploy zichtbaar wordt.

**Wat als "heeft een Redis-URL" telt.** De variabele mag rechtstreeks gezet zijn of via een
`secretref`; beide vormen komen in dit project voor. Het gaat erom dat hij in dezelfde stap wordt
meegegeven als waarin de app wordt aangemaakt of bijgewerkt.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.architecture._ci_workflow import (
    ContainerAppCommando,
    containerapp_commandos,
    secret_namen_per_stap,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github/workflows"


def _worker_deployments() -> list[ContainerAppCommando]:
    """Elke `containerapp create|update` die een app op de worker-image zet.

    **Waarom via de gedeelde ontleding (ADR-036 OP-91/OP-102).** Dit bestand had een eigen,
    tweede tokenizer. Die knipte alleen op voortzettings-backslashes en zocht daarna tekst.
    Twee gevolgen, allebei gemeten op 2026-08-30:

    - de `--yaml`-deployvorm (de scheduler) was volledig onzichtbaar: daar staan de env-vars
      in een heredoc-manifest en niet op de commandoregel;
    - het `containerapp secret set`-commando dat sinds 2026-08-27 de secrets zet, viel buiten
      de scan, waardoor de `update`-tak leek te verwijzen naar een secret dat nergens gevuld
      werd.

    De guard stond daardoor ROOD terwijl de deploy correct was. Een tweede ontleding die een
    ander antwoord geeft dan de eerste is precies de faalvorm waar `_ci_workflow` voor is
    gemaakt; die is nu de enige.
    """
    return [c for c in containerapp_commandos() if "/worker:" in c.image()]


def test_the_scan_finds_worker_deployments_at_all() -> None:
    """Vangnet op een EXPLICIETE verzameling, niet op "de lijst is niet leeg"."""
    gevonden = {f"{c.workflow}:{c.stap}" for c in _worker_deployments()}

    ontbreekt = sorted(
        {
            "cd-staging.yml:Deploy worker",
            "cd-staging.yml:Deploy scheduler",
            "cd-production.yml:Deploy worker",
        }
        - gevonden
    )
    assert not ontbreekt, (
        f"Deze deploystappen zetten geen app meer op de worker-image: {ontbreekt}. Gevonden: "
        f"{sorted(gevonden)}. Is de stap hernoemd of de image-naam veranderd? Zolang een stap "
        "hier ontbreekt bewaakt de test hieronder daar niets."
    )


def test_every_worker_deployment_passes_a_redis_url() -> None:
    """Zonder REDIS_URL start het proces niet, en de deploy meldt toch succes.

    BEIDE helften (ADR-036 OP-107): de env-var EN de secretwaarde. Alleen op de env-var
    toetsen liet toe dat `REDIS_URL=secretref:redis-url` verwees naar een secret dat nergens
    meer wordt gevuld -- bij een `containerapp update` blijft de oude waarde dan staan, dus
    een sleutelrotatie stopt stil met werken.

    De secretwaarde mag in HETZELFDE commando staan (`--secrets`, of de `secrets:`-sectie van
    een `--yaml`-manifest) of in een `containerapp secret set` in DEZELFDE stap. Die tweede
    vorm is geen versoepeling maar de enige mogelijke: `az containerapp update` kent geen
    `--set-secrets`.
    """
    secrets_per_stap = secret_namen_per_stap()
    zonder: list[str] = []

    for commando in _worker_deployments():
        waar = f"{commando.workflow}:{commando.stap} ({commando.actie})"
        waarde = commando.env_vars().get("REDIS_URL")
        if not waarde:
            zonder.append(f"{waar}: geen REDIS_URL in de omgeving")
            continue
        if not waarde.startswith("secretref:"):
            continue
        naam = waarde.split(":", 1)[1]
        bekend = commando.secret_namen() | secrets_per_stap.get(
            (commando.workflow, commando.stap), set()
        )
        if naam not in bekend:
            zonder.append(f"{waar}: verwijst naar secret {naam!r} dat hier nergens wordt gezet")

    assert not zonder, (
        "Deze deploystappen zetten een app op de worker-image zonder werkende REDIS_URL:\n  "
        + "\n  ".join(zonder)
        + "\n\n`src/workers/workflow_worker.py` gooit zonder die variabele een RuntimeError bij "
        "het IMPORTEREN. Het entrypoint is dramatiq, dus er is geen bootcheck die dat netjes "
        "meldt: de container start, valt om, en de deploy meldt succes (ADR-036 OP-87)."
    )


def test_the_redis_url_is_resolved_before_it_is_used() -> None:
    """De bepaalstap moet VOOR de stappen staan die de waarde gebruiken.

    `RESOLVED_REDIS_URL` komt uit `$GITHUB_ENV` en is pas beschikbaar in LATERE stappen. Staat de
    bepaalstap eronder, dan is de variabele leeg en krijgt de app een lege verbindingsstring --
    weer een storing die zich als succes voordoet.
    """
    for workflow in sorted(WORKFLOW_DIR.glob("cd-*.yml")):
        parsed = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
        for jobnaam, job in (parsed.get("jobs") or {}).items():
            stappen = job.get("steps") or []
            bepaalt: int | None = None
            gebruikt: list[int] = []
            for i, step in enumerate(stappen):
                script = str(step.get("run", ""))
                # Twee schrijfvormen: `naam=waarde` en de gedelimiteerde heredoc-vorm
                # `naam<<EOF` (ADR-036 OP-99, tegen newline-injectie). Beide tellen.
                zet_hem = ("RESOLVED_REDIS_URL=" in script or "RESOLVED_REDIS_URL<<" in script)
                if zet_hem and "GITHUB_ENV" in script:
                    bepaalt = i
                elif "${RESOLVED_REDIS_URL}" in script:
                    gebruikt.append(i)

            if bepaalt is None and not gebruikt:
                continue
            assert gebruikt, (
                f"{workflow.name}:{jobnaam} bepaalt RESOLVED_REDIS_URL maar gebruikt hem nergens. "
                "Dan is de bepaalstap dode configuratie en krijgt geen enkele app de waarde."
            )

            assert bepaalt is not None, (
                f"{workflow.name}:{jobnaam} gebruikt RESOLVED_REDIS_URL in stap {gebruikt} maar "
                "zet hem nergens in $GITHUB_ENV. De waarde is dan leeg."
            )
            te_vroeg = [i for i in gebruikt if i < bepaalt]
            assert not te_vroeg, (
                f"{workflow.name}:{jobnaam} gebruikt RESOLVED_REDIS_URL in stap {te_vroeg}, voor "
                f"de bepaalstap op {bepaalt}. Een variabele uit $GITHUB_ENV is pas in LATERE "
                "stappen beschikbaar; hier zou hij leeg zijn."
            )


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_every_dramatiq_worker_pins_its_process_and_thread_count() -> None:
    """Zonder `--processes` en `--threads` start dramatiq zoveel processen als de HOST kernen heeft.

    **Waarom dit een guard is en geen comment (ADR-036 OP-13).** `cpu_count()` telt de kernen
    van de machine, niet de limiet van de container. Op 0,5 vCPU en 1 GiB betekent dat een
    veelvoud aan processen dat gegarandeerd door het geheugen gaat: SIGKILL (exit -9), een
    herstartlus, en een deploy die succes meldt.

    Die twee vlaggen stonden tot 2026-08-30 ALLEEN in Azure -- handmatig gezet, door de
    update-tak keurig behouden, en bij een hercreatie stilzwijgend weg. Precies de vorm van
    fout die je pas ziet als je hem al hebt: er is geen foutmelding, alleen een worker die
    niets verzet.

    De scheduler valt hier buiten: die start met `-m src.workers.scheduler` en is geen
    dramatiq-worker.

    **Mutatietest (2026-08-30, beide richtingen):** `--processes 1` uit het manifest van
    `worker-staging` gehaald -> ROOD met die app in de melding; teruggezet -> GROEN.
    """
    zonder: list[str] = []
    for commando in _worker_deployments():
        argumenten = commando.start_argumenten()
        is_dramatiq = any(":redis_broker" in argument for argument in argumenten)
        if not is_dramatiq:
            continue
        ontbreekt = [vlag for vlag in ("--processes", "--threads") if vlag not in argumenten]
        if ontbreekt:
            zonder.append(f"{commando.workflow}:{commando.stap} ({commando.actie}) mist {ontbreekt}")

    assert not zonder, (
        "Deze dramatiq-workers krijgen geen expliciete proces- en threadgrenzen mee:\n  "
        + "\n  ".join(zonder)
        + "\n\nDramatiq leest dan `cpu_count()` van de HOST en start te veel processen voor de "
        "container-limiet. Gevolg: SIGKILL en een herstartlus, terwijl de deploy succes meldt "
        "(ADR-036 OP-13). Zet ze in het `--yaml`-manifest; `--args` weigert een waarde die met "
        "een streepje begint."
    )
