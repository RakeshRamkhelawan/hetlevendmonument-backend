"""Een dramatiq-werker die zonder brokerverwijzing start consumeert niets (ADR-036 OP-84).

**Hoe dit gevonden is.** OP-76 loste op dat de PLANNER zijn opdrachten naar een geheugenwachtrij
stuurde. De vraag die daarna overbleef was welk proces de `cleanup`-wachtrij zou moeten uitlezen --
op het eerste gezicht een architectuurkeuze. Bij nameten bleek het geen keuze maar een fout.

`src/workers/workflow_worker.py` zet bij het importeren een `StubBroker` als globale broker en
wisselt hem pas om zodra `get_redis_broker()` wordt aangeroepen. De module biedt daarvoor een
`__getattr__`-hook aan die `redis_broker` oplevert -- de bedoelde aanroepvorm is dus
`module:redis_broker`.

Gemeten met dramatiq's eigen `import_broker`, precies zoals de CLI hem aanroept:

    import_broker("src.workers.workflow_worker")               -> StubBroker
    import_broker("src.workers.workflow_worker:redis_broker")  -> RedisBroker, 8 wachtrijen

De Dockerfile-CMD en de compose-opdracht gebruikten de EERSTE vorm. Die werker consumeerde dus
niets uit Redis -- niet alleen `cleanup`, maar alle acht wachtrijen. De zusterwerker in hetzelfde
project doet het wel goed (`src.core.learning.worker:_broker`), wat het verschil meteen zichtbaar
maakt zodra je ernaast legt.

`dramatiq/cli.py::import_broker` valt zonder `:varname` terug op `get_broker()`, en dat is op dat
moment de stub. Er komt geen waarschuwing: de werker start, meldt zich gezond, en doet niets.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = ("docker-compose.yml", "docker-compose.prod.yml")
DOCKERFILE = REPO_ROOT / "Dockerfile"


def _dramatiq_broker_arguments() -> list[tuple[str, str]]:
    """Het EERSTE argument van elke dramatiq-aanroep in een gedeployde opdracht.

    Dat eerste argument is wat `import_broker` krijgt; de rest zijn extra modules. Geeft paren van
    (waar het staat, het argument) terug.
    """
    found: list[tuple[str, str]] = []

    for name in COMPOSE_FILES:
        path = REPO_ROOT / name
        if not path.exists():
            continue
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for service, config in (parsed.get("services") or {}).items():
            if not isinstance(config, dict):
                continue
            for key in ("entrypoint", "command"):
                value = config.get(key)
                if value is None:
                    continue
                tokens = value if isinstance(value, list) else value.split()
                tokens = [str(tok) for tok in tokens]
                # Vorm A: het commando is zelf `dramatiq <broker> ...`
                if "dramatiq" in tokens:
                    idx = tokens.index("dramatiq")
                    if idx + 1 < len(tokens):
                        found.append((f"{name}:{service}", tokens[idx + 1]))
                    continue
                # Vorm B: het entrypoint IS dramatiq (Dockerfile) en `command` levert de
                # argumenten. Dan is het eerste token dat op een module lijkt de broker.
                if key == "command" and tokens and tokens[0].startswith("src."):
                    found.append((f"{name}:{service}", tokens[0]))

    if DOCKERFILE.exists():
        text = DOCKERFILE.read_text(encoding="utf-8")
        # Alleen een CMD die hoort bij een dramatiq-ENTRYPOINT telt.
        if "/usr/local/bin/dramatiq" in text:
            for match in re.finditer(r"^CMD \[(.*?)\]", text, re.M):
                tokens = re.findall(r'"([^"]+)"', match.group(1))
                if tokens and tokens[0].startswith("src."):
                    found.append(("Dockerfile:CMD", tokens[0]))

    return found


def test_the_compose_files_still_exist() -> None:
    """Vangnet PER BESTAND: verdwijnt slechts een van de twee compose-bestanden, dan
    blijft de "niet-leeg"-controle hieronder groen terwijl dat bestand niet meer
    gecontroleerd wordt -- de andere levert nog steeds treffers.
    """
    ontbrekend = [name for name in COMPOSE_FILES if not (REPO_ROOT / name).exists()]
    assert not ontbrekend, (
        f"Deze compose-bestanden bestaan niet meer: {ontbrekend}. Hernoemd of verplaatst? "
        "Werk COMPOSE_FILES bij -- anders controleert deze guard de werkers daarin niet meer."
    )


def test_the_scan_finds_worker_commands_at_all() -> None:
    """Vangnet: loopt de scan leeg, dan bewaakt de test hieronder niets."""
    found = _dramatiq_broker_arguments()

    assert found, (
        "Geen enkele dramatiq-opdracht gevonden in de compose-bestanden of de Dockerfile. Is de "
        "aanroepvorm veranderd? Zolang dit leeg terugkomt zegt de test hieronder niets."
    )


def test_every_worker_names_its_broker_explicitly() -> None:
    """Zonder `:varname` krijgt de werker de StubBroker en consumeert hij niets."""
    zonder_broker = [
        f"{waar} -> {argument}"
        for waar, argument in _dramatiq_broker_arguments()
        if ":" not in argument
    ]

    assert not zonder_broker, (
        f"Deze werkers starten zonder brokerverwijzing: {zonder_broker}.\n\n"
        "`dramatiq/cli.py::import_broker` valt dan terug op `get_broker()`, en dat is op dat "
        "moment de StubBroker die `workflow_worker.py` bij het importeren zet. De werker start, "
        "meldt zich gezond, en consumeert NIETS uit Redis -- zonder waarschuwing. Gebruik de vorm "
        "`module:redis_broker`, zoals `learning-worker` het al doet met "
        "`src.core.learning.worker:_broker`."
    )
