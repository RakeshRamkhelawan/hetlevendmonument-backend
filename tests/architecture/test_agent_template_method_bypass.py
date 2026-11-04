import inspect
import importlib
import pkgutil
import pytest
from src.core.agents.base_agent import EnhancedBaseAgent

#: Zoveel agentklassen stonden er op 2026-09-08 onder src.core.agents (hoofdmap-venv,
#: 0 importfouten). Vloer met ruimte: een module die niet meer importeert mag de scan
#: niet stil laten leegzakken.
_MINIMUM_AGENT_CLASSES = 20


def _scan_agent_classes() -> tuple[list[type], list[str]]:
    """Verzamel alle EnhancedBaseAgent-subklassen onder src.core.agents.

    Retourneert (klassen, fouten). Een module die niet importeert (ontbrekende
    optionele dependency, syntaxfout na een halve refactor) wordt hard gemeld i.p.v.
    stil overgeslagen -- anders blijft precies die module ongecontroleerd voor het
    governance-gate-defect dat deze guard moet vangen (AIACT-ADR023-001).
    """
    import src.core.agents

    agent_classes: list[type] = []
    fouten: list[str] = []

    package = src.core.agents
    for _, module_name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            fouten.append(f"{module_name}: {type(exc).__name__}: {exc}")
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, EnhancedBaseAgent) and obj is not EnhancedBaseAgent:
                agent_classes.append(obj)

    return agent_classes, fouten


@pytest.mark.architecture
def test_no_agent_module_is_silently_unimportable() -> None:
    """Vangnet: een module die niet importeert wordt hier ongecontroleerd voor
    process_task()-overschrijvingen -- dat mag nooit stil blijven."""
    _, fouten = _scan_agent_classes()
    assert not fouten, (
        "De volgende modules onder src.core.agents importeren niet en zijn daardoor NIET "
        "gecontroleerd op een process_task()-overschrijving (AIACT-ADR023-001):\n"
        + "\n".join(f"  - {f}" for f in fouten)
    )


@pytest.mark.architecture
def test_the_scan_actually_finds_agent_classes() -> None:
    """Vangnet: een verplaatst/hernoemd src.core.agents zou de scan stil laten
    leeglopen en de test hieronder triviaal laten slagen."""
    agent_classes, _ = _scan_agent_classes()
    assert len(set(agent_classes)) >= _MINIMUM_AGENT_CLASSES, (
        f"Slechts {len(set(agent_classes))} EnhancedBaseAgent-subklassen gevonden onder "
        f"src.core.agents (verwacht >= {_MINIMUM_AGENT_CLASSES}). Is het pakket verplaatst "
        "of hernoemd? Dan controleert deze guard niets meer."
    )


@pytest.mark.architecture
def test_no_agent_overrides_process_task() -> None:
    """
    Architecture Test (AIACT-ADR023-001):
    EnhancedBaseAgent implements process_task() as a Template Method pattern
    that enforces the Governance Gate. No subclass is allowed to override
    process_task(). They must override _execute_task() instead.
    """
    agent_classes, _ = _scan_agent_classes()

    violators = []
    for cls in set(agent_classes):
        if "process_task" in cls.__dict__:
            violators.append(cls.__name__)

    assert not violators, (
        "The following agent classes override process_task() which bypasses the "
        f"governance gate: {violators}. Subclasses must override _execute_task() instead."
    )
