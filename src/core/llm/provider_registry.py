"""
LLM Provider Registry - Enterprise Plugin System
Auto-discovers and registers all available LLM providers
"""

import importlib
import inspect
import logging
from pathlib import Path
from typing import Optional

from .llm_client import LLMClient

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Centralized registry for all LLM providers.
    Supports auto-discovery and manual registration.
    """

    _providers: dict[str, type[LLMClient]] = {}
    _initialized: bool = False

    @classmethod
    def register(cls, name: str, provider_class: type[LLMClient]) -> None:
        """
        Manually register a provider.

        Example:
            ProviderRegistry.register("custom", CustomProvider)
        """
        cls._providers[name.lower()] = provider_class
        logger.info(f"Registered LLM provider: {name}")

    @classmethod
    def get(cls, name: str) -> type[LLMClient] | None:
        """Get provider class by name"""
        if not cls._initialized:
            cls.auto_discover()
        return cls._providers.get(name.lower())

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered provider names"""
        if not cls._initialized:
            cls.auto_discover()
        return sorted(cls._providers.keys())

    @classmethod
    def auto_discover(cls) -> None:
        """
        Auto-discover all provider classes in llm package.
        Looks for classes ending with 'Provider' that inherit from LLMClient.
        """
        if cls._initialized:
            return

        llm_dir = Path(__file__).parent

        for py_file in llm_dir.glob("*_provider.py"):
            module_name = py_file.stem

            try:
                # Import module dynamically (package relative to src root)
                # Assuming this file is in src.core.llm
                module = importlib.import_module(f"src.core.llm.{module_name}")

                # Find provider classes
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (
                        name.endswith("Provider")
                        and issubclass(obj, LLMClient)
                        and obj is not LLMClient
                    ):
                        # Extract provider name (e.g., "GeminiProvider" -> "gemini")
                        provider_name = name.replace("Provider", "").lower()
                        cls._providers[provider_name] = obj
                        logger.debug(
                            f"Auto-discovered provider: {provider_name} from {module_name}"
                        )

            except Exception as e:
                logger.warning(f"Failed to load provider from {module_name}: {e}")

        cls._initialized = True
        logger.info(f"Provider registry initialized with {len(cls._providers)} providers")


# Lazy initialization: auto_discover() is called on first get() or list_providers()
# NOT at import time, to avoid slowing down startup (B-003 fix).
# See: tests/unit/llm/test_provider_registry_lazy.py
