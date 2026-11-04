"""De boot-check op verplichte productievariabelen draait ook onder blue/green (ADR-036 OP-30).

**De bevinding.** `ConfigValidator.validate()` draaide `_check_production_required_vars()`
alleen als `ENVIRONMENT` `"production"` of `"staging"` was -- terwijl blue/green ook een
productietechniek is (`deployment/blue_green/`). `REDIS_URL` staat al in beide
blue/green-compose-bestanden (gemeten), maar `API_BASE_URL` en `FRONTEND_URL` stonden er
NERGENS in -- niet in de compose-bestanden, niet geinjecteerd door `deploy.py`. Simpelweg de
omgevingsgate verbreden zonder eerst die twee waarden te provisioneren had blue/green-deploys
direct laten falen.

**De waarden.** `.github/workflows/cd-production.yml` gebruikt `https://api.sanskritisetu.org`
/ `https://www.sanskritisetu.org` als de BEDOELDE productie-URL's. Die domeinen resolven op dit
moment niet (geen DNS), bevestigd door Rakesh: er is nog geen live productieomgeving. Het zijn
dus de juiste, toekomstige waarden, niet iets dat vandaag al bereikbaar hoeft te zijn -- de
boot-check test AANWEZIGHEID van de variabele, niet bereikbaarheid van de URL.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.core.config.config_validator import ConfigValidator

_REPO_ROOT = Path(__file__).resolve().parents[4]
_COMPOSE_FILES = (
    _REPO_ROOT / "deployment" / "blue_green" / "docker-compose.blue.yml",
    _REPO_ROOT / "deployment" / "blue_green" / "docker-compose.green.yml",
)


@pytest.mark.unit
class TestTheBootCheckCoversBlueGreen:
    """`_check_production_required_vars` moet ook draaien onder ENVIRONMENT=blue/green."""

    @pytest.mark.parametrize("environment", ["blue", "green"])
    def test_a_missing_api_base_url_is_flagged(self, environment: str) -> None:
        env = {
            "ENVIRONMENT": environment,
            "REDIS_URL": "redis://redis:6379/0",
            "FRONTEND_URL": "https://www.sanskritisetu.org",
            "TOOL_PAYLOAD_PSEUDONYM_KEY": "x" * 32,
        }
        with patch.dict("os.environ", env, clear=False):
            import os

            os.environ.pop("API_BASE_URL", None)
            validator = ConfigValidator()
            result = validator.validate()

        api_base_url_issues = [i for i in result.issues if i.key == "API_BASE_URL"]
        assert api_base_url_issues, (
            f"ENVIRONMENT={environment} zonder API_BASE_URL geeft geen boot-check-fout -- "
            "de omgevingsgate dekt blue/green nog niet."
        )

    @pytest.mark.parametrize("environment", ["blue", "green"])
    def test_a_missing_frontend_url_is_flagged(self, environment: str) -> None:
        env = {
            "ENVIRONMENT": environment,
            "REDIS_URL": "redis://redis:6379/0",
            "API_BASE_URL": "https://api.sanskritisetu.org",
            "TOOL_PAYLOAD_PSEUDONYM_KEY": "x" * 32,
        }
        with patch.dict("os.environ", env, clear=False):
            import os

            os.environ.pop("FRONTEND_URL", None)
            validator = ConfigValidator()
            result = validator.validate()

        frontend_url_issues = [i for i in result.issues if i.key == "FRONTEND_URL"]
        assert frontend_url_issues, (
            f"ENVIRONMENT={environment} zonder FRONTEND_URL geeft geen boot-check-fout -- "
            "de omgevingsgate dekt blue/green nog niet."
        )

    def test_production_and_staging_are_still_covered(self) -> None:
        """Regressiebewijs: de bestaande twee omgevingen mogen niet wegvallen."""
        for environment in ("production", "staging"):
            env = {
                "ENVIRONMENT": environment,
                "REDIS_URL": "redis://redis:6379/0",
                "FRONTEND_URL": "https://www.sanskritisetu.org",
                "TOOL_PAYLOAD_PSEUDONYM_KEY": "x" * 32,
            }
            with patch.dict("os.environ", env, clear=False):
                import os

                os.environ.pop("API_BASE_URL", None)
                validator = ConfigValidator()
                result = validator.validate()

            api_base_url_issues = [i for i in result.issues if i.key == "API_BASE_URL"]
            assert api_base_url_issues, (
                f"ENVIRONMENT={environment} regressie: geen boot-check-fout meer"
            )


@pytest.mark.unit
class TestTheComposeFilesProvisionTheURLs:
    """De compose-bestanden moeten API_BASE_URL/FRONTEND_URL zetten -- anders faalt de
    boot-check hierboven het deploy zodra de gate verbreed is.
    """

    def test_both_compose_files_set_api_base_url_and_frontend_url(self) -> None:
        missing: list[str] = []
        for compose_path in _COMPOSE_FILES:
            text = compose_path.read_text(encoding="utf-8")
            if "API_BASE_URL=" not in text:
                missing.append(f"{compose_path.name}: API_BASE_URL")
            if "FRONTEND_URL=" not in text:
                missing.append(f"{compose_path.name}: FRONTEND_URL")

        assert not missing, (
            "Deze compose-bestanden zetten API_BASE_URL/FRONTEND_URL niet -- de verbrede "
            f"boot-check hierboven zou het deploy laten falen: {missing}"
        )

    def test_both_compose_files_parse_as_valid_yaml(self) -> None:
        """Vangnet: een kapotte YAML-wijziging mag niet stil doorglippen."""
        for compose_path in _COMPOSE_FILES:
            yaml.safe_load(compose_path.read_text(encoding="utf-8"))
