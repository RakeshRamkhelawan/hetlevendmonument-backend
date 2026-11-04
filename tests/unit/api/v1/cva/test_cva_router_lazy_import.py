"""
Lazy-import regression tests for the CVA router.

Verifies that importing the CVA domain router does not eagerly load heavy
modules such as CVAService, LLMService, or UltimateCVAAgent, so that dev
startup stays under ADR-009's 30s budget.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest


@pytest.fixture
def fail_on_heavy_cva_modules() -> Any:
    """Return a side-effect that raises if a heavy CVA module is imported."""
    real_import = __builtins__["__import__"]  # type: ignore[index]
    forbidden = {
        "src.core.services.cva_service",
        "src.core.services.llm.service",
        "src.core.agents.cva_orchestrator",
        "src.core.agents.ultimate_cva.memory",
    }

    def guarded_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> ModuleType:
        if name in forbidden:
            raise AssertionError(
                f"Heavy module {name} was imported while loading CVA router"
            )
        return real_import(name, globals, locals, fromlist, level)

    return guarded_import


@pytest.fixture
def dropped_cva_modules() -> Iterator[None]:
    """Verwijder de CVA-modules uit `sys.modules` en zet ze daarna TERUG (ADR-036 OP-45).

    Deze test moet vanaf een lege importcache beginnen, anders bewijst hij niets over wat het
    importeren van de router aanraakt. Tot 2026-08-04 verwijderde hij die modules zonder ze te
    herstellen, en dat lekte naar elke andere test in dezelfde xdist-worker.

    Wat er dan gebeurt: het opnieuw importeren maakt een NIEUW moduleobject voor
    `src.core.api.v1.cva.legacy_router`, met nieuwe klassen. `src.core.api.cva_endpoints` blijft
    ondertussen in `sys.modules` staan en houdt de OUDE klassen vast (`cva_endpoints.py:5`
    importeert `CVAChatResponse` daarvandaan). Een `is`-vergelijking tussen die twee is daarna
    vals, terwijl beide identiek printen.

    Deterministisch gemeten: in een schone interpreter is
    `cva_endpoints.CVAChatResponse is legacy_router.CVAChatResponse` waar, na dit patroon niet
    meer. Het slachtoffer was
    `tests/unit/test_sp_type01_cva_endpoints_types.py::test_chat_with_cva_returns_cva_chat_response`,
    die de identiteit via `typing.get_type_hints` toetst. Onder xdist bepaalde het TOEVAL of die
    test in dezelfde worker na deze terechtkwam -- vandaar dat de volledige suite per run op een
    andere test leek te falen en elke test los slaagde.

    Herstel in `finally`, zodat het ook gebeurt als de test faalt.
    """
    prefix = "src.core.api.v1.cva"
    saved = {name: module for name, module in sys.modules.items() if name.startswith(prefix)}
    for name in saved:
        del sys.modules[name]
    try:
        yield
    finally:
        # Eerst weg wat de test opnieuw heeft geimporteerd, dan de ORIGINELE objecten terug --
        # anders blijft het nieuwe object naast het oude staan.
        for name in [n for n in list(sys.modules) if n.startswith(prefix)]:
            del sys.modules[name]
        sys.modules.update(saved)


def test_cva_domain_router_imports_without_heavy_modules(
    fail_on_heavy_cva_modules: Any,
    dropped_cva_modules: None,
) -> None:
    """Importing the CVA domain router must not load heavy backend modules."""
    with patch("builtins.__import__", side_effect=fail_on_heavy_cva_modules):
        import src.core.api.v1.cva  # noqa: F401


def test_dropping_the_cva_modules_leaves_no_second_module_object() -> None:
    """De test hierboven mag geen TWEEDE moduleobject achterlaten (ADR-036 OP-45).

    `test_cva_domain_router_imports_without_heavy_modules` verwijdert elke
    `src.core.api.v1.cva*`-sleutel uit `sys.modules` en importeert opnieuw. Zonder herstel is
    `src.core.api.v1.cva.legacy_router` daarna een NIEUW moduleobject met NIEUWE klassen, terwijl
    `src.core.api.cva_endpoints` -- dat nog in `sys.modules` staat -- de OUDE klassen vasthoudt
    (`cva_endpoints.py:5` importeert `CVAChatResponse` daarvandaan).

    Gevolg, deterministisch gemeten: in een schone interpreter is
    `cva_endpoints.CVAChatResponse is legacy_router.CVAChatResponse` waar; na het patroon van de
    test hierboven niet meer. Elke latere test die die identiteit toetst, valt dan om --
    `tests/unit/test_sp_type01_cva_endpoints_types.py::test_chat_with_cva_returns_cva_chat_response`
    doet dat met `typing.get_type_hints`.

    Waarom dit zo lang onzichtbaar bleef: onder xdist bepaalt het TOEVAL of die test in dezelfde
    worker terechtkomt na deze. Daarom faalde de suite per run op een andere test, en slaagde elke
    test los -- exact het beeld dat CLAUDE.md OP-19 aan resource-uitputting toeschrijft, maar hier
    met een andere oorzaak.

    **Deze test drijft de FIXTURE aan (Gate 2 ronde 6, F5).** De eerste versie las alleen de
    identiteit en vertrouwde erop dat hij in dit bestand NA de veroorzaker staat, met als argument
    "dus pytest voert hem in die volgorde uit". Dat geldt alleen serieel. `pyproject.toml` zet geen
    `--dist`, dus xdist draait op `load` en verdeelt LOSSE tests: de reviewer selecteerde alleen
    deze test en kreeg 1 passed terwijl het lek erin zat -- vacuum. En de voorgeschreven
    suite-opdracht is nu juist `-n 4`.

    Nu drijft hij `dropped_cva_modules` zelf aan via `__wrapped__` en toetst hij beide richtingen:
      1. binnen de fixture MOET de identiteit gebroken zijn -- anders is er niets te herstellen en
         is deze guard vacuum;
      2. na de teardown MOET hij weer kloppen -- anders herstelt de fixture niet.

    Bewust de ECHTE fixture en niet het patroon nagebouwd: een nagebouwde drop bewijst alleen dat
    Python werkt zoals Python werkt. Het lek zat in de fixture, dus die hoort onder de loep.

    Mutatie-getest: met `sys.modules.update(saved)` uit de fixture gehaald faalt deze test ook
    wanneer hij ALLEEN geselecteerd is (waar de vorige versie groen bleef).
    """
    import src.core.api.cva_endpoints as endpoints

    prefix = "src.core.api.v1.cva"
    saved = {name: module for name, module in sys.modules.items() if name.startswith(prefix)}
    assert saved, (
        "src.core.api.v1.cva* staat niet in sys.modules, dus de fixture kan niets droppen en deze "
        "guard zou vacuum zijn."
    )
    original = endpoints.CVAChatResponse

    fixture_fn = getattr(dropped_cva_modules, "__wrapped__", None)
    assert fixture_fn is not None, (
        "dropped_cva_modules heeft geen __wrapped__, dus deze test kan de echte fixture niet "
        "aandrijven en zou terugvallen op een nagebouwd patroon. Dat bewijst niets over de fixture."
    )

    generator = fixture_fn()
    entered = False
    try:
        next(generator)  # setup: verwijdert de modules
        entered = True

        import src.core.api.v1.cva.legacy_router as reimported

        assert original is not reimported.CVAChatResponse, (
            "Het opnieuw importeren binnen de fixture levert DEZELFDE klasse op. Dan is er geen lek "
            "om te herstellen en is deze guard vacuum geworden -- of de fixture raakt niet meer de "
            "modules die cva_endpoints re-exporteert. Zoek uit welke van de twee voordat je deze "
            "assertie aanpast; groen maken door haar te verwijderen brengt OP-45 terug."
        )

        with pytest.raises(StopIteration):
            next(generator)  # teardown: MOET herstellen
        entered = False

        from src.core.api.v1.cva.legacy_router import CVAChatResponse

        assert endpoints.CVAChatResponse is CVAChatResponse, (
            "Na de teardown van dropped_cva_modules is de klasse-identiteit nog steeds gebroken: "
            f"cva_endpoints houdt {id(endpoints.CVAChatResponse)}, sys.modules heeft "
            f"{id(CVAChatResponse)}. De fixture zet sys.modules dus niet terug, en elke latere test "
            "in dezelfde xdist-worker ziet een andere klasse dan de module die hem re-exporteert. "
            "Dat is OP-45: de suite faalt dan per run op een ANDERE test en elke test slaagt los."
        )
    finally:
        if entered:  # de fixture is niet netjes afgerond -- zelf opruimen
            generator.close()
        for name in [n for n in list(sys.modules) if n.startswith(prefix)]:
            del sys.modules[name]
        sys.modules.update(saved)
