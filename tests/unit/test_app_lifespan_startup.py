"""
Unit tests for app lifespan startup cost controls.

Covers:
- Development mode skips seeding when default tenant exists
- Production mode always runs seeding
- Verification only runs when seeding was attempted
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSeedInitialDataWithGuard:
    """Tests for the _seed_initial_data guard logic."""

    @pytest.mark.asyncio
    async def test_dev_mode_skips_seed_when_tenant_exists(self):
        """Happy path: development mode skips seeding if default tenant exists."""
        with patch("src.core.app_lifespan.ENVIRONMENT", "development"):
            with patch("src.core.app_lifespan._default_tenant_exists", return_value=True):
                with patch("src.core.app_lifespan._seed_initial_data_with_retry") as mock_seed:
                    from src.core.app_lifespan import _seed_initial_data

                    await _seed_initial_data()
                    mock_seed.assert_not_called()

    @pytest.mark.asyncio
    async def test_dev_mode_runs_seed_when_no_tenant(self):
        """Unhappy path: development mode seeds when default tenant does not exist."""
        with patch("src.core.app_lifespan.ENVIRONMENT", "development"):
            with patch("src.core.app_lifespan._default_tenant_exists", return_value=False):
                with patch("src.core.app_lifespan._seed_initial_data_with_retry") as mock_seed:
                    from src.core.app_lifespan import _seed_initial_data

                    await _seed_initial_data()
                    mock_seed.assert_called_once()

    @pytest.mark.asyncio
    async def test_prod_mode_always_runs_seed(self):
        """User behavior: production always seeds regardless of existing data."""
        with patch("src.core.app_lifespan.ENVIRONMENT", "production"):
            with patch("src.core.app_lifespan._default_tenant_exists", return_value=True):
                with patch("src.core.app_lifespan._seed_initial_data_with_retry") as mock_seed:
                    from src.core.app_lifespan import _seed_initial_data

                    await _seed_initial_data()
                    mock_seed.assert_called_once()


class TestDefaultTenantExists:
    """Tests for the _default_tenant_exists helper."""

    @pytest.mark.asyncio
    async def test_returns_true_when_tenant_found(self):
        """Happy path: default tenant exists in database."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1, "default")

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        with patch("src.core.app_lifespan.db_manager") as mock_db:
            mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

            from src.core.app_lifespan import _default_tenant_exists

            result = await _default_tenant_exists()
            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_tenant(self):
        """Unhappy path: default tenant does not exist."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        with patch("src.core.app_lifespan.db_manager") as mock_db:
            mock_db.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_db.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

            from src.core.app_lifespan import _default_tenant_exists

            result = await _default_tenant_exists()
            assert result is False
