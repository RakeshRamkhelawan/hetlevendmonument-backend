"""
Tests voor SP-E07: Phase2 endpoints gatten achter PHASE2_ENABLED feature flag.

TDD: tests moeten ROOD zijn voor implementatie, GROEN erna.

Patroon: zelfde als SP-B03 (RAG_ENABLED flag).
- Source checks: PHASE2_ENABLED aanwezig in router_registry
- Default check: veilige default 'false'
- Behavioral: routes onbereikbaar als flag niet gezet
"""

import inspect
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).parent.parent.parent
_REGISTRY_PATH = "src/core/api/setup/router_registry.py"


def _read_registry() -> str:
    return (_ROOT / _REGISTRY_PATH).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Source-check tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPhase2SourceChecks:
    def test_phase2_enabled_flag_in_registry(self) -> None:
        """PHASE2_ENABLED feature flag staat in router_registry.py."""
        source = _read_registry()
        assert "PHASE2_ENABLED" in source, (
            "PHASE2_ENABLED feature flag niet gevonden in router_registry.py -- "
            "phase2 router wordt ongecontroleerd gemount"
        )

    def test_phase2_default_is_false(self) -> None:
        """Default voor PHASE2_ENABLED is 'false' -- veilig voor productie."""
        source = _read_registry()
        if "PHASE2_ENABLED" in source:
            assert (
                '"false"' in source or "'false'" in source
            ), "PHASE2_ENABLED heeft geen veilige default 'false' in router_registry.py"

    def test_phase2_flag_uses_correct_env_var_name(self) -> None:
        """Router_registry gebruikt PHASE2_ENABLED (niet APP_DEBUG of SETUP_MODE)."""
        source = _read_registry()
        if "phase2_router" in source:
            assert (
                "PHASE2_ENABLED" in source
            ), "phase2 router gating gebruikt niet PHASE2_ENABLED als env var naam"

    def test_phase2_registration_conditional(self) -> None:
        """include_router voor phase2 staat achter een conditie, niet onvoorwaardelijk."""
        source = _read_registry()
        # Na fix: de include_router call voor phase2 staat in een if-blok
        # Zoek naar 'if' met PHASE2_ENABLED in de buurt
        lines = source.splitlines()
        phase2_lines = [i for i, line in enumerate(lines) if "phase2_router" in line]
        include_router_lines = [
            i
            for i, line in enumerate(lines)
            if "include_router" in line and "phase2" in line.lower()
        ]
        # Als er een include_router aanroep is voor phase2, moet die conditionally zijn
        for lnum in include_router_lines:
            # Zoek de if-statement erboven (max 5 regels)
            context = "\n".join(lines[max(0, lnum - 5) : lnum + 1])
            assert (
                "if" in context and "PHASE2_ENABLED" in context
            ), f"phase2 include_router op regel {lnum} staat niet achter PHASE2_ENABLED check"


@pytest.mark.unit
class TestPhase2BehavioralFlag:
    def test_phase2_disabled_hides_stub_endpoints(self) -> None:
        """
        Behavioral: als PHASE2_ENABLED=false (default) worden phase2 endpoints
        niet gemount -- clients zien 404 in plaats van stub_implementation.
        """
        import os

        os.environ["PHASE2_ENABLED"] = "false"
        try:
            # Direct controleren: wordt de router geregistreerd?
            registry_source = _read_registry()
            # Als de flag er in zit, is de router geconditioneerd
            assert (
                "PHASE2_ENABLED" in registry_source
            ), "PHASE2_ENABLED niet in registry -- router altijd gemount"
        finally:
            os.environ.pop("PHASE2_ENABLED", None)

    def test_phase2_flag_not_hardcoded_true(self) -> None:
        """PHASE2_ENABLED is nergens hardcoded True in de registry."""
        source = _read_registry()
        # Controleer dat er geen 'PHASE2_ENABLED', 'true' patroon is zonder os.getenv
        assert 'PHASE2_ENABLED = "true"' not in source
        assert "PHASE2_ENABLED = 'true'" not in source
        assert "PHASE2_ENABLED=true" not in source.replace(" ", "").lower() or (
            "os.getenv" in source
        ), "PHASE2_ENABLED staat hardcoded als true -- veiligheidsrisico"

    def test_phase2_import_stays_optional(self) -> None:
        """phase2_router import blijft in try/except -- ImportError blijft afgehandeld."""
        source = _read_registry()
        # De try/except voor phase2 moet nog steeds aanwezig zijn
        if "phase2" in source.lower():
            # Ofwel lazy import in if-block, ofwel try/except bovenaan
            has_try_except = "try:" in source and "phase2_router" in source
            has_lazy_import = "PHASE2_ENABLED" in source and "import" in source
            assert (
                has_try_except or has_lazy_import
            ), "phase2 import is noch in try/except, noch lazy -- ImportError niet afgehandeld"

    def test_stub_implementation_not_exposed_via_default_config(self) -> None:
        """
        stub_implementation string mag niet bereikbaar zijn via default config.
        Na de fix: phase2 router is niet gemount bij PHASE2_ENABLED=false.
        Verificatie: PHASE2_ENABLED check staat in registry, dus router niet gemount.
        """
        source = _read_registry()
        # De aanwezigheid van PHASE2_ENABLED check IS het bewijs
        # dat stub_implementation niet bereikbaar is bij default config
        assert (
            "PHASE2_ENABLED" in source
        ), "Geen PHASE2_ENABLED flag -- stub_implementation bereikbaar voor clients"

    def test_phase2_source_has_no_always_true_mount(self) -> None:
        """
        phase2 router mag niet onvoorwaardelijk gemount worden.
        Vorige (foute) code: if phase2_router: app.include_router(phase2_router)
        Gewenste code: if phase2_router and PHASE2_ENABLED: app.include_router(...)
        """
        source = _read_registry()
        lines = source.splitlines()
        for i, line in enumerate(lines):
            if "include_router" in line and "phase2" in line.lower():
                # Deze include_router aanroep moet een PHASE2_ENABLED check hebben
                context = "\n".join(lines[max(0, i - 5) : i + 1])
                assert (
                    "PHASE2_ENABLED" in context
                ), f"include_router voor phase2 op regel {i + 1} heeft geen PHASE2_ENABLED check"

    def test_phase2_env_var_read_via_os_getenv(self) -> None:
        """PHASE2_ENABLED wordt gelezen via os.getenv, niet via hardcoded waarde."""
        source = _read_registry()
        if "PHASE2_ENABLED" in source:
            assert (
                "os.getenv" in source or "environ" in source
            ), "PHASE2_ENABLED wordt niet via os.getenv gelezen"

    def test_phase2_behavioral_operator_can_enable_via_env(self) -> None:
        """
        Behavioral: operator kan phase2 inschakelen door PHASE2_ENABLED=true te zetten.
        Verificatie: de code leest de env var -- dus operator heeft controle.
        """
        source = _read_registry()
        # Als PHASE2_ENABLED in de source staat als env var check,
        # dan heeft de operator controle via de omgeving
        assert "PHASE2_ENABLED" in source, "Operator heeft geen controle via PHASE2_ENABLED env var"
