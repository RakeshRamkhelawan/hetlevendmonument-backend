"""De OpenAPI-oppervlakte is dicht buiten development (ADR-036 OP-124).

`create_app()` leest de module-global `src.main.ENVIRONMENT` (`src/main.py:118`), niet
`os.getenv`. `patch.object` is daarom voldoende EN zelfherstellend; er is geen
`importlib.reload` nodig. Dat is bewust, want een reload van `src.main`:

  1. voert `configure_logging()` opnieuw uit en bindt een nieuwe loguru-sink aan de
     per-test afgevangen stdout van de xdist-worker -- precies wat `tests/conftest.py`
     weghaalt om `ValueError: I/O operation on closed file` te voorkomen;
  2. voert `app = create_app()` (`src/main.py:239`) opnieuw uit en vervangt
     `src.main.app`, terwijl 43 testbestanden plus `tests/conftest.py` namen uit die
     module op moduleniveau vasthouden (de OP-45-klasse);
  3. kan `validate_config_at_startup()` bereiken (`src/main.py:55-56` slaat die alleen
     over bij `TESTING=1` of een gezette `PYTEST_CURRENT_TEST`), en die doet
     `sys.exit(1)` -- een dode xdist-worker, wat zich voordoet als de OP-19-signatuur
     "elke run een andere test FAILED".

De fail-secure default wordt daarom structureel getoetst, niet door de module te
herladen: een reload roept `setup_environment()` aan, die `.env.local` met
`override=True` inleest, en dan hangt de uitkomst af van een untracked bestand in
plaats van van de code.

Mutatie-bewijs (daadwerkelijk gedraaid, zie de final-approver brief van 2026-08-14):

  - `docs_url="/docs"` onvoorwaardelijk in `src/main.py`
        -> test_docs_are_closed_outside_development[production] FAILED
  - `is_development = ENVIRONMENT != "production"` (fail-open voor staging)
        -> test_docs_are_closed_outside_development[staging] FAILED
  - `docs_url=None` onvoorwaardelijk
        -> test_docs_are_open_in_development FAILED
  - default in `os.getenv("ENVIRONMENT", ...)` terug naar `"development"`
        -> test_the_environment_default_is_fail_secure FAILED
"""

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

import src.main

MAIN_PY = Path(src.main.__file__)

# Elke waarde die niet exact "development" is hoort de docs dicht te houden. `staging`,
# `blue` en `green` staan er expliciet in omdat de CD-workflows die zetten; de laatste
# is een onbekende waarde, want een fail-secure default moet ook een typefout dichthouden.
NIET_DEVELOPMENT = ["production", "staging", "test", "blue", "green", "acceptatie-onbekend"]


class TestOpenApiSurfaceIsClosedOutsideDevelopment:
    """De drie schema-endpoints staan alleen open in development."""

    @pytest.mark.parametrize("omgeving", NIET_DEVELOPMENT)
    def test_docs_are_closed_outside_development(self, omgeving: str) -> None:
        with patch.object(src.main, "ENVIRONMENT", omgeving):
            app = src.main.create_app(testing=True)

        assert (app.docs_url, app.redoc_url, app.openapi_url) == (None, None, None), (
            f"ENVIRONMENT={omgeving!r} moet /docs, /redoc en /openapi.json dichthouden. "
            "Zie ADR-036 OP-124: een open schema legt de volledige API-oppervlakte bloot "
            "aan een onauthenticated verzoek."
        )

    def test_docs_are_open_in_development(self) -> None:
        """De andere richting: zonder deze test is 'weiger alles' een geldige fix."""
        with patch.object(src.main, "ENVIRONMENT", "development"):
            app = src.main.create_app(testing=True)

        assert (app.docs_url, app.redoc_url, app.openapi_url) == (
            "/docs",
            "/redoc",
            "/openapi.json",
        ), "development moet de docs juist WEL serveren, anders is de guard een sloophamer."

    def test_the_environment_default_is_fail_secure(self) -> None:
        """Een ontbrekende ENVIRONMENT-variabele valt terug op `production`, niet development.

        Structureel getoetst op de AST van `src/main.py`: geen import van de module,
        geen reload, en dus immuun voor `.env`-bestanden en shell-state.
        """
        boom = ast.parse(MAIN_PY.read_text(encoding="utf-8"))

        defaults = [
            knoop.args[1].value
            for knoop in ast.walk(boom)
            if isinstance(knoop, ast.Call)
            and isinstance(knoop.func, ast.Attribute)
            and knoop.func.attr == "getenv"
            and len(knoop.args) == 2
            and isinstance(knoop.args[0], ast.Constant)
            and knoop.args[0].value == "ENVIRONMENT"
            and isinstance(knoop.args[1], ast.Constant)
        ]

        assert defaults == ["production"], (
            "src/main.py moet ENVIRONMENT precies eenmaal opvragen met default 'production'; "
            f"gevonden: {defaults!r}. Een default van 'development' zet de docs open zodra de "
            "variabele ontbreekt -- fail-open op precies de storing die telt (ADR-036 OP-124)."
        )
