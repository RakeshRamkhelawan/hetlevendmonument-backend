"""
Architecture test: production compose must declare LLM config, never plaintext keys.

Finding: LLM-ADR26-001
"""

from pathlib import Path

import pytest
import yaml


@pytest.mark.unit
def test_prod_compose_declares_llm_provider_config() -> None:
    """docker-compose.prod.yml must source LLM secrets from env/Key Vault."""
    compose_path = Path("docker-compose.prod.yml")
    assert compose_path.exists(), "docker-compose.prod.yml is missing"

    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose.get("services", {})

    required_vars = {
        "LLM_PROVIDER",
        "DEFAULT_LLM_MODEL",
        "LLM_MODEL",
        # Mistral (EU) in plaats van DeepSeek (ADR-041 B14, besluit Rakesh 2026-10-15).
        "MISTRAL_API_KEY",
        "LLM_FALLBACK_PROVIDER",
        "GEMINI_API_KEY",
    }

    # The backend and the learning worker both need LLM runtime config.
    covered_services = {"backend", "learning-worker"}
    for service_name in covered_services:
        service = services.get(service_name, {})
        env_block = service.get("environment", [])

        env_values: dict[str, str] = {}
        for entry in env_block:
            if isinstance(entry, str) and "=" in entry:
                key, value = entry.split("=", 1)
                env_values[key] = value

        missing = required_vars - set(env_values.keys())
        assert not missing, f"{service_name} missing LLM env vars: {missing}"
        assert "DEEPSEEK_API_KEY" not in env_values, (
            f"{service_name} zet DeepSeek weer neer; klantgegevens gaan naar Mistral (EU)"
        )

        for var in required_vars:
            value = env_values[var]
            assert value.startswith("${"), (
                f"{service_name}.{var} must be sourced from env, got: {value}"
            )
            assert "}" in value, (
                f"{service_name}.{var} has malformed env substitution: {value}"
            )
            # Hardcoded secrets are forbidden.
            assert "sk-" not in value, (
                f"{service_name}.{var} looks like a hardcoded API key"
            )
