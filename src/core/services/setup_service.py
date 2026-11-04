import logging
from pathlib import Path
from typing import Any

import httpx

from src.core.exceptions import ValidatieFout
from src.core.shared.config import (
    get_setup_artifact_name,
    get_setup_artifact_path,
    is_setup_mode_enabled,
)

logger = logging.getLogger(__name__)


class SetupService:
    def _get_bootstrap_artifact_path(self) -> Path:
        """Resolve the only reviewed bootstrap artifact path allowed for setup writes."""
        configured_path = get_setup_artifact_path()
        reviewed_name = get_setup_artifact_name()

        if configured_path != reviewed_name:
            raise ValidatieFout(
                f"Setup bootstrap artifact must be exactly '{reviewed_name}' in the application root"
            )

        return Path.cwd() / reviewed_name

    def artifact_name(self) -> str:
        """Return the safe bootstrap artifact name for client-facing responses."""
        return get_setup_artifact_name()

    def setup_artifact_exists(self) -> bool:
        """Return whether setup has already produced the reviewed bootstrap artifact."""
        return self._get_bootstrap_artifact_path().exists()

    async def validate_openai_key(self, api_key: str) -> bool:
        """
        Validates the OpenAI API key by making a minimal request.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Error validating OpenAI key: {e}")
            return False

    def write_env_file(self, configs: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """
        Write setup output to the reviewed bootstrap artifact only in setup mode.
        """
        if not is_setup_mode_enabled():
            raise PermissionError("Setup mode is disabled")

        env_path = self._get_bootstrap_artifact_path()

        new_lines: list[str] = []
        for key, value in configs.items():
            normalized_value = "" if value is None else str(value)
            if "\n" in normalized_value or "\r" in normalized_value:
                raise ValueError("Configuration values must not contain newlines")
            new_lines.append(f"{key}={normalized_value}\n")

        with open(env_path, "x", encoding="utf-8") as f:
            f.writelines(new_lines)
