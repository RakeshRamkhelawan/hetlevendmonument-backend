from pathlib import Path

import pytest

from src.core.config.compose_runtime_contract import (
    ComposeRuntimeContractValidator,
    validate_compose_runtime_contract,
)


def test_validate_compose_runtime_contract_happy_path(tmp_path: Path) -> None:
    compose_file = tmp_path / "docker-compose.e2e.yml"
    compose_file.write_text(
        """
services:
  playwright:
    environment:
      - BASE_URL=http://host.docker.internal:5174
      - API_URL=http://host.docker.internal:8110
      - CI=true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = validate_compose_runtime_contract(compose_file)

    assert result.valid is True
    assert result.issues == []


def test_validate_compose_runtime_contract_happy_path_dict_environment(tmp_path: Path) -> None:
        compose_file = tmp_path / "docker-compose.e2e.yml"
        compose_file.write_text(
                """
services:
    playwright:
        environment:
            BASE_URL: http://host.docker.internal:5174
            API_URL: http://host.docker.internal:8110
            CI: "true"
""".strip()
                + "\n",
                encoding="utf-8",
        )

        result = validate_compose_runtime_contract(compose_file)

        assert result.valid is True
        assert result.issues == []


def test_validate_compose_runtime_contract_unhappy_path_flags_backend_port_mismatch(
    tmp_path: Path,
) -> None:
    compose_file = tmp_path / "docker-compose.e2e.yml"
    compose_file.write_text(
        """
services:
  playwright:
    environment:
      - BASE_URL=http://host.docker.internal:5174
      - API_URL=http://host.docker.internal:8001
      - CI=true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = validate_compose_runtime_contract(compose_file)

    assert result.valid is False
    assert any(issue.key == "playwright.API_URL" for issue in result.issues)


def test_validate_compose_runtime_contract_unhappy_path_flags_missing_base_url(
        tmp_path: Path,
) -> None:
        compose_file = tmp_path / "docker-compose.e2e.yml"
        compose_file.write_text(
                """
services:
    playwright:
        environment:
            - API_URL=http://host.docker.internal:8110
            - CI=true
""".strip()
                + "\n",
                encoding="utf-8",
        )

        result = validate_compose_runtime_contract(compose_file)

        assert result.valid is False
        assert any(issue.key == "playwright.BASE_URL" for issue in result.issues)


@pytest.mark.unit
def test_repo_e2e_compose_matches_runtime_contract() -> None:
    compose_file = Path(__file__).resolve().parents[2] / "docker-compose.e2e.yml"

    result = ComposeRuntimeContractValidator().validate_file(compose_file)

    assert result.valid is True, [issue.message for issue in result.issues]