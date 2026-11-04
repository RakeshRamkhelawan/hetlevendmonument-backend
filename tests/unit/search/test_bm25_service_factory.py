"""
Test: BM25Service factory pattern.
Verifies that no I/O happens at import time and factory returns singleton.
"""

import pytest
from unittest.mock import patch


@pytest.mark.unit
class TestBM25ServiceFactory:
    """BE-UTL-040: BM25Service must use lazy factory, no I/O at import."""

    def test_factory_returns_singleton(self) -> None:
        """get_bm25_service() must return the same instance on multiple calls."""
        from src.core.search.bm25_service import get_bm25_service

        svc1 = get_bm25_service()
        svc2 = get_bm25_service()
        assert svc1 is svc2

    def test_no_io_at_import(self) -> None:
        """Importing the module must not trigger mkdir or file operations."""
        import importlib
        import sys

        mod_name = "src.core.search.bm25_service"
        # Save and restore sys.modules so we don't leave a new module object behind.
        # If the original is replaced, subsequent patches of this module's names
        # (e.g. get_redis_client) operate on the NEW object while BM25Service
        # methods still look up globals in the ORIGINAL object's __dict__ —
        # causing order-dependent test failures elsewhere in the suite.
        saved = sys.modules.get(mod_name)
        try:
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            with patch("pathlib.Path.mkdir") as mock_mkdir:
                importlib.import_module(mod_name)
                mock_mkdir.assert_not_called()
        finally:
            if saved is not None:
                sys.modules[mod_name] = saved
            elif mod_name in sys.modules:
                del sys.modules[mod_name]

    def test_lazy_init_triggers_on_first_use(self) -> None:
        """First call to get_bm25_service() must instantiate BM25Service."""
        import importlib
        import sys

        mod_name = "src.core.search.bm25_service"
        # Save and restore sys.modules — see test_no_io_at_import for rationale.
        saved = sys.modules.get(mod_name)
        try:
            if mod_name in sys.modules:
                del sys.modules[mod_name]

            mod = importlib.import_module(mod_name)
            # Reset singleton so we can observe first-call behavior
            mod._bm25_service_instance = None

            with patch.object(mod, "BM25Service") as mock_cls:
                mock_instance = mock_cls.return_value
                mod.get_bm25_service()
                mock_cls.assert_called_once()
        finally:
            if saved is not None:
                sys.modules[mod_name] = saved
            elif mod_name in sys.modules:
                del sys.modules[mod_name]
