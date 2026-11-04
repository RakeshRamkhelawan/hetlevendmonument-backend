"""
Test: ProviderRegistry lazy discovery.
Verifies that auto_discover does NOT run at import time.
"""

import pytest
from unittest.mock import patch


@pytest.mark.unit
class TestProviderRegistryLazyDiscovery:
    """BE-UTL-039: ProviderRegistry must not auto-discover at import time."""

    def test_no_auto_discover_at_import(self) -> None:
        """Re-importing the module must not trigger auto_discover."""
        import importlib
        import sys

        from src.core.llm import provider_registry

        # sys.modules bewaren en terugzetten, net als in
        # tests/unit/search/test_bm25_service_factory.py. Zonder dat herstel blijft er een NIEUW
        # moduleobject achter: modules die er al een klasse uit hadden geimporteerd houden de oude
        # objecten vast, terwijl een latere importeur nieuwe maakt. Een `isinstance` in een ander
        # testbestand faalt dan zonder zichtbare reden, en alleen bij een bepaalde volgorde --
        # de vorm van ADR-036 OP-45. Het tests/conftest.py-vangnet betrapte deze test daarop op
        # 2026-08-11.
        naam = "src.core.llm.provider_registry"
        bewaard = sys.modules.get(naam)
        try:
            with patch.object(provider_registry.ProviderRegistry, "auto_discover") as mock_discover:
                # Force re-import
                sys.modules.pop(naam, None)
                importlib.import_module(naam)
                mock_discover.assert_not_called()
        finally:
            if bewaard is not None:
                sys.modules[naam] = bewaard
            else:
                sys.modules.pop(naam, None)

    def test_get_triggers_lazy_discovery(self) -> None:
        """Calling get() without prior auto_discover must trigger it."""
        from src.core.llm.provider_registry import ProviderRegistry

        # Reset state
        ProviderRegistry._initialized = False
        ProviderRegistry._providers = {}

        with patch.object(ProviderRegistry, "auto_discover", wraps=ProviderRegistry.auto_discover) as mock_discover:
            ProviderRegistry.get("deepseek")
            mock_discover.assert_called_once()

    def test_list_providers_triggers_lazy_discovery(self) -> None:
        """Calling list_providers() without prior auto_discover must trigger it."""
        from src.core.llm.provider_registry import ProviderRegistry

        # Reset state
        ProviderRegistry._initialized = False
        ProviderRegistry._providers = {}

        with patch.object(ProviderRegistry, "auto_discover", wraps=ProviderRegistry.auto_discover) as mock_discover:
            ProviderRegistry.list_providers()
            mock_discover.assert_called_once()

    def test_auto_discover_is_idempotent(self) -> None:
        """Second call to auto_discover must be a no-op."""
        from src.core.llm.provider_registry import ProviderRegistry

        # Reset and run once
        ProviderRegistry._initialized = False
        ProviderRegistry._providers = {}

        with patch.object(ProviderRegistry, "auto_discover", wraps=ProviderRegistry.auto_discover) as mock_discover:
            ProviderRegistry.get("deepseek")
            ProviderRegistry.get("deepseek")
            # auto_discover should only be called once (by first get)
            assert mock_discover.call_count == 1
