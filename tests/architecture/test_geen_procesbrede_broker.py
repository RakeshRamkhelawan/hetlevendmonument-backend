"""Geen procesbrede dramatiq-broker en geen StubBroker in `src/` (ADR-036 OP-13, brief 2026-10-21).

**Wat er mis was.** `src/workers/workflow_worker.py` riep bij het importeren `dramatiq.set_broker(StubBroker())` aan.
Elke actor met een kale `@dramatiq.actor` bond bij decoratie aan die stub; een `.send()` in een proces dat de echte
broker niet had gebonden (elk API-proces) belandde in een geheugenwachtrij die niemand uitleest. Geen fout, geen
uitvoering. Het oudere `test_dramatiq_broker_isolation.py` bewaakte alleen `set_broker()` op MODULENIVEAU en kende de
workflow-worker als uitzondering; die uitzondering was het gat.

**Drie regels, voor alle bestanden onder `src/`:**
1. Geen aanroep van `set_broker(...)`, op welke diepte ook (ook in een functie, ook met een alias).
2. Geen aanroep van `StubBroker(...)`. Een `isinstance(x, StubBroker)` is wel toegestaan (de scheduler gebruikt dat om
   een foute broker te WEIGEREN). Tests hebben een stub nodig en krijgen hem via een fixture in `tests/conftest.py`.
3. Geen `@dramatiq.actor` zonder `broker=`: die bindt aan de procesbrede `get_broker()`. Gebruik
   `workflow_actor` uit `src/core/tasks/dramatiq_broker.py`, of geef een eigen broker mee (leerwerker, bonlezer).

**Mutatiebewijs, per regel en in beide richtingen:** `TestDeMeting` voert `vind_overtredingen` uit op losse
bronteksten: `set_broker` in een functie, via een alias, als attribuut -> gevonden; `StubBroker(` direct, via een
alias, via het volledige pad -> gevonden; een kale `@dramatiq.actor` en `@dramatiq.actor(queue_name=...)` ->
gevonden. Legitiem en NIET gevonden: `isinstance(x, StubBroker)`, `get_broker()`, `@dramatiq.actor(broker=b)`,
`@workflow_actor`. De test op de echte boom is groen na de reparatie en was ROOD op 8fdb38cb
(`workflow_worker.py:209-210`, kale actors).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_ROOT = Path("src")

#: `bestand` -> reden. Leeg: er is geen enkele reden meer voor een stub of een procesbrede broker in `src/`.
KNOWN_UITZONDERINGEN: dict[str, str] = {}


def vind_overtredingen(bron: str) -> list[tuple[int, str]]:
    """(regel, wat) voor elke overtreding van de drie regels in deze brontekst."""
    boom = ast.parse(bron)

    # Namen onder een alias geimporteerd: `from dramatiq import set_broker as sb`.
    alias: dict[str, str] = {}
    module_namen = {
        "dramatiq",
        "dramatiq_module",
    }  # namen waaronder de dramatiq-module in dit bestand staat
    actor_namen: set[str] = set()  # `from dramatiq import actor [as x]`
    for knoop in ast.walk(boom):
        if (
            isinstance(knoop, ast.ImportFrom)
            and knoop.module
            and knoop.module.startswith("dramatiq")
        ):
            for naam in knoop.names:
                if naam.name in ("set_broker", "StubBroker"):
                    alias[naam.asname or naam.name] = naam.name
                if naam.name == "actor" and knoop.module == "dramatiq":
                    actor_namen.add(naam.asname or naam.name)
        if isinstance(knoop, ast.Import):
            for naam in knoop.names:
                if naam.name == "dramatiq":
                    module_namen.add(naam.asname or naam.name)

    def _doelnaam(functie: ast.expr) -> str | None:
        if isinstance(functie, ast.Attribute):
            return functie.attr
        if isinstance(functie, ast.Name):
            return alias.get(functie.id, functie.id)
        return None

    def _is_dramatiq_actor(doel: ast.expr) -> bool:
        """`dramatiq.actor`, `dq.actor` (import-alias) of een kale `actor` uit `from dramatiq import actor`."""
        if isinstance(doel, ast.Name):
            return doel.id in actor_namen
        return (
            isinstance(doel, ast.Attribute)
            and doel.attr == "actor"
            and isinstance(doel.value, ast.Name)
            and doel.value.id in module_namen
        )

    def _heeft_echte_broker(aanroep: ast.Call) -> bool:
        """Een `broker=`-trefwoord dat niet `None` is en niet `get_broker()` (dat IS de procesbrede broker).

        `**kw` telt niet: daar is niet te zien of er een broker in zit.
        """
        for k in aanroep.keywords:
            if k.arg != "broker":
                continue
            if isinstance(k.value, ast.Constant) and k.value.value is None:
                return False
            if isinstance(k.value, ast.Call) and _doelnaam(k.value.func) == "get_broker":
                return False
            return True
        return False

    gevonden: list[tuple[int, str]] = []
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.Call):
            doel = _doelnaam(knoop.func)
            if doel == "set_broker":
                gevonden.append((knoop.lineno, "set_broker()"))
            elif doel == "StubBroker":
                gevonden.append((knoop.lineno, "StubBroker()"))
            elif _is_dramatiq_actor(knoop.func) and not _heeft_echte_broker(knoop):
                # Ook buiten een decorator-positie: `x = dramatiq_module.actor(max_retries=1)` bindt even goed
                # aan de procesbrede broker.
                gevonden.append((knoop.lineno, "@dramatiq.actor zonder broker="))
        if isinstance(knoop, ast.FunctionDef | ast.AsyncFunctionDef):
            for dec in knoop.decorator_list:
                if not isinstance(dec, ast.Call) and _is_dramatiq_actor(
                    dec
                ):  # kale `@dramatiq.actor`
                    gevonden.append((dec.lineno, "@dramatiq.actor zonder broker="))
    return gevonden


def _scan_src() -> tuple[dict[str, list[tuple[int, str]]], list[str]]:
    gevonden: dict[str, list[tuple[int, str]]] = {}
    fouten: list[str] = []
    for pad in sorted(SRC_ROOT.rglob("*.py")):
        try:
            tekst = pad.read_text(encoding="utf-8-sig")
            hits = vind_overtredingen(tekst)
        except (OSError, SyntaxError, UnicodeDecodeError) as fout:
            fouten.append(f"{pad.as_posix()}: {fout}")
            continue
        if hits:
            gevonden[pad.as_posix()] = hits
    return gevonden, fouten


class TestDeBoom:
    def test_de_scan_ziet_alle_bestanden_en_slaat_er_geen_over(self) -> None:
        aantal = len(list(SRC_ROOT.rglob("*.py")))
        _, fouten = _scan_src()

        assert (aantal >= 1500, fouten) == (True, [])

    def test_geen_set_broker_geen_stubbroker_geen_kale_actor_in_src(self) -> None:
        gevonden, _ = _scan_src()
        nieuw = {pad: hits for pad, hits in gevonden.items() if pad not in KNOWN_UITZONDERINGEN}

        regels = [f"  - {pad}:{n} {wat}" for pad, hits in sorted(nieuw.items()) for n, wat in hits]
        assert regels == [], (
            "Een procesbrede broker, een StubBroker of een actor zonder eigen broker in `src/` laat een `.send()` "
            "stilletjes op een wachtrij landen die niemand uitleest (ADR-036 OP-13):\n"
            + "\n".join(regels)
            + "\n\nBind de actor aan `workflow_broker` via `workflow_actor` "
            "(src/core/tasks/dramatiq_broker.py) of geef een eigen broker mee."
        )

    def test_de_uitzonderingslijst_is_niet_verouderd(self) -> None:
        gevonden, _ = _scan_src()
        verouderd = sorted(pad for pad in KNOWN_UITZONDERINGEN if pad not in gevonden)

        assert verouderd == []

    def test_elke_uitzondering_heeft_een_reden(self) -> None:
        # Geen `parametrize` over de lijst: is die leeg, dan maakt pytest er een overgeslagen item `[NOTSET]` van en telt de
        # ratel op tests die nooit draaien (CI-run 39852524654) die als een uitgezette test. Een gewone test draait altijd.
        zonder_reden = sorted(
            pad for pad, reden in KNOWN_UITZONDERINGEN.items() if len(reden.strip()) < 25
        )

        assert zonder_reden == []


class TestDeMeting:
    """De meetfunctie op losse bronteksten: per regel en per vorm, beide richtingen."""

    @pytest.mark.parametrize(
        ("bron", "wat"),
        [
            ("import dramatiq\ndef f(b):\n    dramatiq.set_broker(b)\n", "set_broker()"),
            ("from dramatiq import set_broker\nset_broker(1)\n", "set_broker()"),
            ("from dramatiq import set_broker as sb\nsb(1)\n", "set_broker()"),
            ("m.set_broker(1)\n", "set_broker()"),
            ("from dramatiq.brokers.stub import StubBroker\nb = StubBroker()\n", "StubBroker()"),
            ("from dramatiq.brokers.stub import StubBroker as S\nb = S()\n", "StubBroker()"),
            ("import dramatiq\nb = dramatiq.brokers.stub.StubBroker()\n", "StubBroker()"),
            ("import dramatiq\n@dramatiq.actor\ndef f(): ...\n", "@dramatiq.actor zonder broker="),
            ("import dramatiq as dq\n@dq.actor\ndef f(): ...\n", "@dramatiq.actor zonder broker="),
            (
                "import dramatiq as dq\n@dq.actor(queue_name='q')\ndef f(): ...\n",
                "@dramatiq.actor zonder broker=",
            ),
            (
                "from dramatiq import actor\n@actor\ndef f(): ...\n",
                "@dramatiq.actor zonder broker=",
            ),
            (
                "from dramatiq import actor\n@actor(queue_name='q')\ndef f(): ...\n",
                "@dramatiq.actor zonder broker=",
            ),
            (
                "from dramatiq import actor as a\n@a(max_retries=1)\ndef f(): ...\n",
                "@dramatiq.actor zonder broker=",
            ),
            (
                "import dramatiq\n@dramatiq.actor(broker=None)\ndef f(): ...\n",
                "@dramatiq.actor zonder broker=",
            ),
            (
                "import dramatiq\n@dramatiq.actor(broker=dramatiq.get_broker())\ndef f(): ...\n",
                "@dramatiq.actor zonder broker=",
            ),
            (
                "import dramatiq\n@dramatiq.actor(**kw)\ndef f(): ...\n",
                "@dramatiq.actor zonder broker=",
            ),
            (
                "import dramatiq\n@dramatiq.actor(queue_name='x')\ndef f(): ...\n",
                "@dramatiq.actor zonder broker=",
            ),
            (
                "import dramatiq as dramatiq_module\n@dramatiq_module.actor(max_retries=1)\ndef f(): ...\n",
                "@dramatiq.actor zonder broker=",
            ),
        ],
    )
    def test_een_overtreding_wordt_gevonden(self, bron: str, wat: str) -> None:
        assert [w for _, w in vind_overtredingen(bron)] == [wat]

    @pytest.mark.parametrize(
        "bron",
        [
            "from dramatiq.brokers.stub import StubBroker\ndef f(b):\n    return isinstance(b, StubBroker)\n",
            "import dramatiq\nb = dramatiq.get_broker()\n",
            "import dramatiq\n@dramatiq.actor(broker=b, max_retries=1)\ndef f(): ...\n",
            "from x import workflow_actor\n@workflow_actor\ndef f(): ...\n",
            "import dramatiq as dq\n@dq.actor(broker=b)\ndef f(): ...\n",
            "from dramatiq import actor\n@actor(broker=b)\ndef f(): ...\n",
            "from other import actor\n@actor\ndef f(): ...\n",
            "from x import workflow_actor\n@workflow_actor(queue_name='q')\ndef f(): ...\n",
            "# dramatiq.set_broker(b) staat hier alleen als commentaar\nx = 1\n",
            "def f():\n    '''Roep set_broker() niet aan.'''\n",
        ],
    )
    def test_een_legitiem_geval_wordt_niet_gevonden(self, bron: str) -> None:
        assert vind_overtredingen(bron) == []
