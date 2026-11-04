"""Elk gedeployed worker-image moet kunnen STARTEN met de omgeving die de deploy meegeeft.

**De bevinding (ADR-036 OP-91, opnieuw geopend 2026-08-09).** `cd-production.yml` zet op de
scheduler- en de worker-stap wel `ENVIRONMENT=production`, maar geen `API_BASE_URL` en geen
`SERENA_API_URL`. `src/config.py:39-52` is een fail-fast-blok dat precies op die twee afgaat:

    ValueError: API_BASE_URL environment variable required in production
    ValueError: SERENA_API_URL cannot contain localhost in production

De tweede is niet te vermijden door de variabele weg te laten -- `os.getenv` heeft daar
`http://localhost:8001` als default, dus NIET zetten garandeert de uitzondering.

Azure meldt zo'n deploy als GESLAAGD; de container crash-loopt vervolgens eeuwig. Er komt geen
foutmelding wanneer iets NIET gebeurt. OP-91 stond in de ADR en in het reviewdoc als gesloten
terwijl dit gat er nog was.

**Waarom deze test het echte importpad draait en niet alleen `Config()`.** `Config()`
construeren is een PROXY voor wat er misging. De crash zat in `python -m src.workers.scheduler`,
via `src/workers/__init__.py` -> `actors.py` -> `workflow_tasks.py` -> `autonomous_agent.py` ->
`database/redis.py` -> `src/config.py:187` (`config = Config()` op moduleniveau). Zou een
volgende import een DERDE variabele nodig hebben, dan blijft een `Config()`-toets groen terwijl
de planner nog steeds niet start. Dus: het echte `import src.workers.scheduler`, in een vers
proces met exact de gedeployde omgeving.

**Wat de test WEL en NIET bewijst.** Wel: met de env-vars die de workflow zet, komt het
importpad door zijn fail-fast-controles. Niet: dat de bijbehorende Azure-secrets ook echt
bestaan -- `secretref:...` wordt hier ingevuld met een plaatsvervanger, want de waarde zelf
zit in Azure en niet in deze repo. Een ontbrekend secret is een andere bevinding met een eigen
guard (`test_worker_apps_get_a_redis_url.py`).

**Mutatietest (2026-08-09, beide richtingen, 4/4 zoals verwacht):**

| Mutatie op `cd-production.yml` | Verwacht | Gemeten |
| --- | --- | --- |
| `API_BASE_URL` uit de CREATE-tak van `Deploy scheduler (productie)` | ROOD | ROOD |
| `SERENA_API_URL` uit de worker-stap | ROOD | ROOD |
| LEGITIEM: een ongerelateerde `LOG_LEVEL=INFO` erbij | GROEN | GROEN |
| De hele stap `Deploy scheduler (productie)` verwijderd | ROOD | ROOD |

**Twee keer heeft die mutatietest deze guard afgekeurd, en dat hoort hier te staan** -- beide
keren was hij groen gebleven onder precies de mutatie die hij moest vangen:

1. *Eerst voegde ik create- en update-tak samen tot EEN omgeving per app.* Dan verbergt de
   update-tak een ontbrekende `API_BASE_URL` in de create-tak, terwijl die twee elkaar
   UITSLUITEN: bij de eerste deploy bestaat de app nog niet en draait alleen `create`. Nu
   worden beide bereikbare toestanden los getoetst.
2. *Daarna telde het vangnet SCENARIO'S in plaats van APPS.* Het verwijderen van de complete
   scheduler-stap liet het aantal scenario's boven de drempel, dus groen. Nu telt het per
   omgeving het aantal onderscheiden apps, en dat moeten er twee zijn (worker en planner).

Beide zijn dezelfde faalvorm als de guards die deze sprintdag repareert: er werd iets geteld
dat meebewoog met de mutatie in plaats van het ANTWOORD dat de guard hoort te bewaken.

**Addendum 2026-08-26 (OP-112).** `src/config.py`'s SERENA_API_URL-fail-fast-check is nu
voorwaardelijk op `ENABLE_SERENA_MCP` (dat nergens in de CD-workflows gezet wordt, dus default
`false`). Rij 2 van de mutatietabel hierboven ("SERENA_API_URL uit de worker-stap -> ROOD") was
correct op 2026-08-09 maar is met deze wijziging niet langer de reden dat een deploy crasht --
zonder MCP aan wordt de check overgeslagen en start het proces ook zonder die variabele. Deze
test blijft ongewijzigd GROEN, want de CD-workflow zet `SERENA_API_URL=https://serena.invalid`
nog steeds expliciet (nu overbodig voor het booten, maar onschadelijk) -- geverifieerd door
deze testfile daadwerkelijk te draaien na de config.py-wijziging: 3 passed. Blijft ENABLE_
SERENA_MCP=true ooit gezet worden voor een worker-app, dan geldt de fail-fast-check daar weer
onverkort.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tests.architecture._ci_workflow import REPO_ROOT, containerapp_commandos

#: Het image dat de python-codebase draait. Zowel de worker als de scheduler gebruiken dit;
#: ze verschillen alleen in startcommando. Selecteren op IMAGE en niet op appnaam: een
#: hernoemde app valt dan niet stil buiten de scan.
_WORKER_IMAGE_MERKER = "/worker:"

#: Plaatsvervangers voor waarden die in Azure staan. Bewust niet-localhost en herkenbaar.
_SECRETREF_INVULLING = {
    "DATABASE_URL": "postgresql+asyncpg://u:p@db.postgres.database.azure.com:5432/ss",
    "REDIS_URL": "rediss://:sleutel@cache.redis.cache.windows.net:6380/0",
}
_STANDAARD_INVULLING = "azure-secret-plaatsvervanger"


def _gedeployde_omgevingen() -> list[tuple[str, dict[str, str]]]:
    """Per gedeployde APP: (herkomst, de omgeving die deze repo erop zet).

    **Per app en niet per commando, want `--set-env-vars` is een PATCH.** `az containerapp
    update --set-env-vars` werkt de genoemde variabelen bij en laat de rest staan; alleen de
    `create`-tak schrijft de volledige definitie. Een `update`-tak los beoordelen zou dus elke
    app afkeuren die zijn database in de `create`-tak krijgt -- dat was de eerste versie van
    deze test, en die had staging ten onrechte rood gemeld.

    Samenvoegen per appnaam geeft wat DEZE REPO over die app vastlegt. Blijft er dan iets
    ontbreken, dan hangt het draaien af van een waarde die ooit met de hand in Azure is gezet
    en nergens in versiebeheer staat. Dat is geen detail: `worker-staging` is op 2026-08-09 in
    Azure gemeten met NUL omgevingsvariabelen.
    """
    create_env: dict[str, dict[str, str]] = {}
    update_env: dict[str, dict[str, str]] = {}
    for commando in containerapp_commandos():
        if _WORKER_IMAGE_MERKER not in commando.image():
            continue
        app = f"{commando.workflow}:{commando.naam()}"
        doel = create_env if commando.actie == "create" else update_env
        doel.setdefault(app, {}).update(commando.env_vars())

    scenarios: list[tuple[str, dict[str, str]]] = []
    for app in sorted(set(create_env) | set(update_env)):
        eerste = create_env.get(app)
        vervolg = update_env.get(app)
        if eerste is not None:
            # De ALLEREERSTE deploy: de app bestaat nog niet, dus alleen de create-tak telt.
            # Deze los toetsen is geen overdaad -- de mutatietest van 2026-08-09 liet zien dat
            # een samengevoegde set een ontbrekende `API_BASE_URL` in de create-tak verbergt
            # achter de update-tak, terwijl die twee elkaar UITSLUITEN.
            scenarios.append((f"{app} (eerste deploy, create)", dict(eerste)))
            if vervolg is not None:
                scenarios.append((f"{app} (vervolgdeploy, create+update)", {**eerste, **vervolg}))
        elif vervolg is not None:
            # Geen create-tak: deze repo legt de omgeving van die app NERGENS volledig vast.
            scenarios.append((f"{app} (alleen update, geen create-tak)", dict(vervolg)))
    return scenarios


def _gedeployde_apps() -> dict[str, set[str]]:
    """Per CD-workflow: de namen van de apps die op het worker-image draaien."""
    per_workflow: dict[str, set[str]] = {}
    for commando in containerapp_commandos():
        if _WORKER_IMAGE_MERKER not in commando.image():
            continue
        per_workflow.setdefault(commando.workflow, set()).add(commando.naam())
    return per_workflow


def _materialiseer(omgeving: dict[str, str]) -> dict[str, str]:
    """`secretref:x` vervangen door een plausibele, niet-localhost waarde."""
    concreet: dict[str, str] = {}
    for naam, waarde in omgeving.items():
        if waarde.startswith("secretref:"):
            concreet[naam] = _SECRETREF_INVULLING.get(naam, _STANDAARD_INVULLING)
        else:
            concreet[naam] = waarde
    return concreet


def _start_in_vers_proces(omgeving: dict[str, str]) -> tuple[int, str]:
    """`import src.workers.scheduler` met exact deze omgeving. Geeft (returncode, stderr)."""
    script = (
        "import sys; sys.path.insert(0, r'"
        + str(REPO_ROOT)
        + "');\n"
        + "import src.workers.scheduler\n"
    )
    resultaat = subprocess.run(
        [sys.executable, "-c", script],
        env={
            **omgeving,
            "PATH": _oorspronkelijk_pad(),
            "SYSTEMROOT": "C:\\Windows",
            "PYTHONIOENCODING": "utf-8",
        },
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(REPO_ROOT),
        check=False,
    )
    return resultaat.returncode, resultaat.stderr


def _oorspronkelijk_pad() -> str:
    import os

    return os.environ.get("PATH", "")


def test_the_scan_finds_the_deployed_worker_images() -> None:
    """Vangnet op het ANTWOORD, niet op de lijst (ADR-036 HIGH-3).

    Een vangnet dat alleen "de lijst is niet leeg" toetst, laat het verwijderen van de
    productie-scheduler ongemerkt door zolang staging er nog een heeft. Dat is letterlijk de
    OP-91-faalvorm een laag hoger. Daarom een EXPLICIETE eis per workflow.
    """
    per_workflow = _gedeployde_apps()

    ontbreekt = sorted({"cd-production.yml", "cd-staging.yml"} - set(per_workflow))
    assert not ontbreekt, (
        f"Deze CD-workflows deployen geen enkel worker-image meer: {ontbreekt}. Gevonden: "
        f"{ {k: sorted(v) for k, v in per_workflow.items()} }. Is de stap verwijderd, hernoemd, "
        "of het image-pad veranderd? Zolang een workflow hier ontbreekt bewaakt de boottest "
        "daar niets."
    )

    # Twee APPS per omgeving, geen twee scenario's: worker en scheduler draaien hetzelfde
    # image met een ander startcommando. Tellen op scenario's liet het VERWIJDEREN van de
    # complete scheduler-stap groen -- gemeten bij de mutatietest van 2026-08-09.
    te_weinig = sorted(
        f"{workflow} ({sorted(apps)})" for workflow, apps in per_workflow.items() if len(apps) < 2
    )
    assert not te_weinig, (
        f"Deze omgevingen deployen minder dan twee worker-image-apps: {te_weinig}. Verwacht "
        "zijn er twee -- de worker en de planner. Ontbreekt de planner, dan draait daar geen "
        "enkele opruimactor en verloopt geen enkel HITL-ticket (ADR-036 OP-91)."
    )


def test_every_deployed_worker_image_carries_an_environment() -> None:
    """Nog een vangnet: een lege env-set zou de boottest betekenisloos maken.

    Zonder deze toets zou het WEGHALEN van `--set-env-vars` de boottest groen maken: geen
    `ENVIRONMENT=production` betekent dat het fail-fast-blok in `src/config.py:39` wordt
    overgeslagen en alles "start".
    """
    zonder = [
        herkomst for herkomst, omgeving in _gedeployde_omgevingen() if "ENVIRONMENT" not in omgeving
    ]

    assert not zonder, (
        f"Deze deploys zetten geen ENVIRONMENT op het worker-image: {zonder}. Dan valt de app "
        "terug op de development-defaults en zegt de boottest hieronder niets."
    )


@pytest.mark.slow
# Deze toets start elk workerimage in een VERS proces (regel 159-169, met een eigen
# subprocess-timeout van 300s). Dat duurt van nature lang: gemeten 2026-09-11 op deze
# machine 24,7s in een rustige poortronde en 82,4s los, en met vier xdist-werkers naast
# elkaar loopt hij over de 60s die de poort als --timeout meegeeft. Hij viel daardoor om
# met "+++ Timeout +++" op een traag moment en was groen op een rustig moment -- een
# uitslag die van de machinebelasting afhangt in plaats van van de code. Eigen ruimere
# limiet in plaats van de poort-timeout verhogen: dat laatste zou elke andere test ook
# langer laten hangen voordat hij opgeeft.
@pytest.mark.timeout(600)
def test_every_deployed_worker_image_actually_boots() -> None:
    """De kern: met exact de gedeployde omgeving moet het importpad het halen.

    Per UNIEKE omgeving een vers proces (ongeveer 16 seconden per stuk), want een tweede
    import in hetzelfde proces meet niets -- de module zit dan in `sys.modules` en de globale
    prometheus-registry gooit bij herregistratie. Die val is bij het opstellen van deze test
    zelf ingelopen en leverde een niet-bestaand "derde struikelblok" op.
    """
    gezien: dict[str, str] = {}
    for herkomst, omgeving in _gedeployde_omgevingen():
        concreet = _materialiseer(omgeving)
        sleutel = json.dumps(concreet, sort_keys=True)
        gezien.setdefault(sleutel, herkomst)

    mislukt: list[str] = []
    for sleutel, herkomst in gezien.items():
        returncode, stderr = _start_in_vers_proces(json.loads(sleutel))
        if returncode != 0:
            laatste = [r for r in stderr.strip().splitlines() if r.strip()]
            mislukt.append(f"{herkomst}: {laatste[-1] if laatste else 'onbekende fout'}")

    assert not mislukt, (
        "Deze gedeployde processen kunnen met hun eigen omgeving niet starten:\n  "
        + "\n  ".join(mislukt)
        + "\n\nAzure meldt zo'n deploy als geslaagd en de container crash-loopt daarna eeuwig. "
        "Er komt geen foutmelding wanneer iets NIET gebeurt (ADR-036 OP-91)."
    )
