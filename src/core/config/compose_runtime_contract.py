from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


@dataclass(frozen=True)
class ComposeContractIssue:
    key: str
    message: str
    current_value: Any = None
    expected_value: Any = None


@dataclass(frozen=True)
class ComposeContractValidationResult:
    valid: bool
    issues: list[ComposeContractIssue] = field(default_factory=list)


class ComposeRuntimeContractValidator:
    def __init__(self, frontend_port: int = 5174, backend_port: int = 8110) -> None:
        self._frontend_port = frontend_port
        self._backend_port = backend_port

    def validate_file(self, file_path: str | Path) -> ComposeContractValidationResult:
        compose_path = Path(file_path)
        data = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
        return self.validate_data(data)

    def validate_data(self, data: dict[str, Any]) -> ComposeContractValidationResult:  # TODO(TYPE): replace Any with concrete type
        issues: list[ComposeContractIssue] = []
        services = data.get("services") or {}
        playwright = services.get("playwright") or {}
        environment = self._normalize_environment(playwright.get("environment"))

        base_url = environment.get("BASE_URL")
        api_url = environment.get("API_URL")

        self._validate_url_port(
            issues=issues,
            key="playwright.BASE_URL",
            value=base_url,
            expected_port=self._frontend_port,
        )
        self._validate_url_port(
            issues=issues,
            key="playwright.API_URL",
            value=api_url,
            expected_port=self._backend_port,
        )

        return ComposeContractValidationResult(valid=not issues, issues=issues)

    @staticmethod
    def _normalize_environment(environment: Any) -> dict[str, str]:  # TODO(TYPE): replace Any with concrete type
        if environment is None:
            return {}
        if isinstance(environment, dict):
            return {str(key): str(value) for key, value in environment.items()}

        result: dict[str, str] = {}
        for item in environment:
            if not isinstance(item, str) or "=" not in item:
                continue
            key, value = item.split("=", 1)
            result[key] = value
        return result

    def _validate_url_port(
        self,
        issues: list[ComposeContractIssue],
        key: str,
        value: str | None,
        expected_port: int,
    ) -> None:
        if not value:
            issues.append(
                ComposeContractIssue(
                    key=key,
                    message=f"{key} is missing from compose environment",
                    current_value=value,
                    expected_value=f"port {expected_port}",
                )
            )
            return

        parsed = urlparse(value)
        if parsed.port != expected_port:
            issues.append(
                ComposeContractIssue(
                    key=key,
                    message=f"{key} must target port {expected_port}",
                    current_value=value,
                    expected_value=expected_port,
                )
            )


def validate_compose_runtime_contract(
    file_path: str | Path,
    frontend_port: int = 5174,
    backend_port: int = 8110,
) -> ComposeContractValidationResult:
    validator = ComposeRuntimeContractValidator(
        frontend_port=frontend_port,
        backend_port=backend_port,
    )
    return validator.validate_file(file_path)