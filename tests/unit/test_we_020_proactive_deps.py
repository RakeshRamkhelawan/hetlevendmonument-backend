"""WE-020/021: ProactiveScheduler app.state dependencies tests."""

import inspect

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.unit
class TestProactiveDeps:
    def test_dbtenant_repo_has_list_active_ids(self) -> None:
        from src.core.copilot.proactive.deps import _DBTenantRepo

        assert hasattr(_DBTenantRepo, "list_active_ids")

    def test_dbtenant_repo_has_get_primary_admin_user_id(self) -> None:
        from src.core.copilot.proactive.deps import _DBTenantRepo

        assert hasattr(_DBTenantRepo, "get_primary_admin_user_id")

    def test_proactive_service_proxy_has_submit_proactive_proposal(self) -> None:
        from src.core.copilot.proactive.deps import _ProactiveServiceProxy

        assert hasattr(_ProactiveServiceProxy, "submit_proactive_proposal")

    def test_init_proactive_deps_called_before_scheduler_in_lifespan(self) -> None:
        """_init_proactive_deps is called before _init_proactive_scheduler."""
        with open("src/core/app_lifespan.py", encoding="utf-8") as f:
            content = f.read()
        idx_deps = content.find("_init_proactive_deps")
        idx_sched = content.find("_init_proactive_scheduler(app)")
        assert idx_deps != -1
        assert idx_sched != -1
        # deps call appears before scheduler call
        assert idx_deps < idx_sched

    def test_init_proactive_deps_defined_in_lifespan(self) -> None:
        with open("src/core/app_lifespan.py", encoding="utf-8") as f:
            content = f.read()
        assert "async def _init_proactive_deps" in content

    async def test_dbtenant_repo_calls_session_factory(self) -> None:
        """_DBTenantRepo.list_active_ids calls the session factory."""
        from src.core.copilot.proactive.deps import _DBTenantRepo

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [1, 2, 3]

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        mock_factory = MagicMock(return_value=mock_db)

        repo = _DBTenantRepo(session_factory=mock_factory)
        result = await repo.list_active_ids()

        assert mock_factory.called
        assert result == [1, 2, 3]
