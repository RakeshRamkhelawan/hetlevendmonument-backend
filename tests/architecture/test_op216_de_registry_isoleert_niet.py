"""ADR-036 OP-216 (GESLOTEN, Route A): de tool-registry bouwt geen Docker-sandbox meer.

**Geschiedenis.** Tot 2026-09-09 dwongen 44 rode unittests iemand om naar
`LocalToolRegistry.__init__` te kijken: die constructor bouwde een `ProductionSandboxManager`,
en die opende een ECHTE verbinding naar de Docker-daemon. Dat werd met
`tests/fixtures/docker_sandbox.py` opgelost (OP-214) -- maar daarmee verdween ook het ENIGE
signaal dat de onderliggende fout nog bestond, dus deze test werd als `xfail(strict=True)`
toegevoegd om die druk mechanisch vast te houden totdat OP-216 zelf gerepareerd was.

**2026-09-10, gerepareerd (Route A).** `LocalToolRegistry` voert sinds OP-126 geen shell/
subprocess-commando's meer uit -- er is dus niets meer om te sandboxen. De dode
`ProductionSandboxManager`-constructie, de nooit-bestaande subprocess-terugval in de logregel
en de onware "executes within the sandbox"-docstringbelofte zijn verwijderd
(`src/core/tool_broker/local_registry.py`). De `xfail`-marker is daarom weg: dit is nu een
gewone regressiebewaker die ROOD moet worden als iemand ooit weer eager een sandbox-daemon
aan deze constructor hangt.

Dit is met opzet GEEN test van de docstringtekst. Een tekstuele toets zou groen worden zodra
iemand het woord `sandbox` ergens laat staan, terwijl het gedrag verandert. De assertie
hieronder gaat over het gedrag: raakt de constructor de Docker-daemon, ja of nee.

**Waarom de assertie niet aan EEN naad hangt.** `from_env` op nul tellen zou ook slagen als
iemand de constructie verbouwt naar `docker.DockerClient(...)`, en dan zou deze test "veilig"
melden terwijl de daemon alsnog wordt geraakt. Daarom worden alle drie de clientvormen geteld
EN wordt het waarneembare gevolg getoetst: is er na de constructie een `sandbox_manager`
gebouwd.

**Mutatiebewijs (verplicht bij een gewijzigde guard, quality-gates.md).** Route A tijdelijk
teruggedraaid (de oude `sandbox_manager`-constructie in `__init__` teruggeplakt in een
werkkopie): deze test faalt dan weer precies zoals voor de fix (`aanroepen=1,
gebouwd=True != (0, False)`) -- bevestigt dat de assertie het echte gedrag meet, niet een
toevallige bijkomstigheid. Legitiem geval (huidige, gefixte code): GROEN, gemeten hieronder.
"""

from __future__ import annotations

from unittest.mock import patch


def test_een_toolregistry_bouwen_raakt_de_docker_daemon_niet() -> None:
    """Een tool-registry bouwen hoort geen daemonverbinding te kosten.

    `docker.from_env` wordt hier gepatcht, dus deze test opent zelf niets -- hij TELT alleen of
    de constructor die functie aanroept.
    """
    import docker

    from src.core.tool_broker.local_registry import LocalToolRegistry

    with (
        patch.object(docker, "from_env") as van_omgeving,
        patch.object(docker, "DockerClient") as via_klasse,
        patch.object(docker, "APIClient") as via_api,
    ):
        registry = LocalToolRegistry()

    aanroepen = van_omgeving.call_count + via_klasse.call_count + via_api.call_count
    gebouwd = getattr(registry, "sandbox_manager", None) is not None

    assert (aanroepen, gebouwd) == (0, False), (
        "LocalToolRegistry.__init__ raakte de Docker-daemon: %d clientconstructie(s), "
        "sandbox_manager gebouwd=%s. Zie ADR-036 OP-216 en de docstring van dit bestand."
        % (aanroepen, gebouwd)
    )
