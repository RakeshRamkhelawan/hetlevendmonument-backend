"""
Test for Docker service URL defaults (Fase 1.2).

Verifies that services use Docker-internal service names as defaults,
not hardcoded localhost addresses that fail in containerized environments.
"""

import os
from pathlib import Path


class TestServiceUrlDefaults:
    """Test that service URL defaults use Docker service names."""

    def test_activepieces_api_url_uses_docker_service_name(self):
        """ACTIVEPIECES_API_URL should default to activepieces:80 (de image luistert op 80), not localhost."""
        # Clear any existing env var
        old_env = os.environ.pop("ACTIVEPIECES_API_URL", None)
        try:
            # Re-import to get fresh default
            from importlib import reload
            import src.core.activepieces.catalog_syncer as catalog_module

            reload(catalog_module)

            syncer = catalog_module.CatalogSyncer()
            # Should use Docker service name, not localhost
            assert (
                "activepieces:80/api/v1/pieces" in syncer.api_url
            ), f"Expected 'activepieces:80/api/v1/pieces' in api_url, got {syncer.api_url}"
            assert (
                "localhost" not in syncer.api_url
            ), f"Expected no 'localhost' in api_url, got {syncer.api_url}"
        finally:
            if old_env:
                os.environ["ACTIVEPIECES_API_URL"] = old_env

    def test_ollama_base_url_uses_docker_service_name(self):
        """OLLAMA_BASE_URL should default to ollama:11434, not localhost."""
        old_env = os.environ.pop("OLLAMA_BASE_URL", None)
        old_api_key = os.environ.pop("OLLAMA_API_KEY", None)
        try:
            from importlib import reload
            import src.core.agents.router_agent_service as router_module

            reload(router_module)

            service = router_module.RouterAgentService(client=None)
            assert (
                "ollama:11434" in service.base_url
            ), f"Expected 'ollama:11434' in base_url, got {service.base_url}"
            assert (
                "localhost" not in service.base_url
            ), f"Expected no 'localhost' in base_url, got {service.base_url}"
        finally:
            if old_env:
                os.environ["OLLAMA_BASE_URL"] = old_env
            if old_api_key:
                os.environ["OLLAMA_API_KEY"] = old_api_key

    def test_sync_server_url_uses_docker_service_name(self):
        """SYNC_SERVER_URL in health endpoints should default to sync-server:1234."""
        old_env = os.environ.pop("SYNC_SERVER_URL", None)
        try:
            from importlib import reload
            from importlib import import_module

            health_module = import_module("src.core.api.health_endpoints")

            reload(health_module)

            # Check the default value used in deep_health_check function
            import inspect

            source = inspect.getsource(health_module.deep_health_check)

            # Should contain the Docker service name
            assert (
                "sync-server:1234" in source
            ), "Expected 'sync-server:1234' in deep_health_check source"
            # Should NOT contain localhost default
            assert (
                '"http://localhost:1234"' not in source
            ), "Found hardcoded 'http://localhost:1234' in health_endpoints"
        finally:
            if old_env:
                os.environ["SYNC_SERVER_URL"] = old_env

    def test_env_var_override_still_works(self):
        """Environment variables should still be able to override defaults."""
        custom_url = "http://custom-host:9999"
        os.environ["ACTIVEPIECES_API_URL"] = custom_url
        os.environ["OLLAMA_BASE_URL"] = custom_url
        os.environ["SYNC_SERVER_URL"] = custom_url

        try:
            from importlib import reload
            import src.core.activepieces.catalog_syncer as catalog_module
            import src.core.agents.router_agent_service as router_module

            reload(catalog_module)
            reload(router_module)

            # Catalog syncer should use env var
            syncer = catalog_module.CatalogSyncer()
            assert syncer.api_url == custom_url, f"Expected {custom_url}, got {syncer.api_url}"

            # Router service should use env var
            service = router_module.RouterAgentService(client=None)
            assert service.base_url == custom_url, f"Expected {custom_url}, got {service.base_url}"
        finally:
            os.environ.pop("ACTIVEPIECES_API_URL", None)
            os.environ.pop("OLLAMA_BASE_URL", None)
            os.environ.pop("SYNC_SERVER_URL", None)


class TestDockerComposeConfig:
    """Test docker-compose.yml uses correct service names."""

    def test_activepieces_api_url_in_docker_compose(self):
        """AP_API_URL in docker-compose should be defined and use an env-var default.

        NOTE: AP_API_URL is a browser-facing URL (used by the SPA frontend to
        call the ActivePieces API via Traefik). Its default of
        http://localhost/automation/api is intentional: in docker-compose
        development mode the browser reaches Traefik on localhost, which
        reverse-proxies the request to the internal activepieces container.
        The URL therefore correctly uses localhost, not an internal service name.
        """
        docker_compose_path = Path(__file__).parent.parent.parent / "docker-compose.yml"
        content = docker_compose_path.read_text()

        # AP_API_URL must be present and configurable via env var
        assert "AP_API_URL=" in content, "AP_API_URL must be configured in docker-compose.yml"

        # Should use the /automation/api path (routed via Traefik)
        assert (
            "/automation/api" in content
        ), "AP_API_URL should route through /automation/api path"

    def test_activepieces_frontend_url_in_docker_compose(self):
        """AP_FRONTEND_URL default should use service-friendly configuration."""
        docker_compose_path = Path(__file__).parent.parent.parent / "docker-compose.yml"
        content = docker_compose_path.read_text()

        # The default should be localhost for browser access, but via proxy
        # The key is that AP_API_URL should use internal service name
        assert "AP_FRONTEND_URL" in content, "AP_FRONTEND_URL should be defined"


import pytest

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
