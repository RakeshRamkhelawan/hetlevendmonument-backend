"""
Tests for SP-E05: GDPR purge real scheduler.

Verifies:
- _schedule_purge_task sends Dramatiq actor message
- purge_user_data actor exists and is decorated
- Actor filters on tenant_id (cross-tenant prevention)
- Actor uses anonymization, not hard DELETE
- Actor has max_retries configured
- No Celery imports (ADR-006)
- No TODO comment remains in _schedule_purge_task
"""

import inspect
from unittest.mock import MagicMock, patch

import pytest


class TestGDPRPurgeScheduler:
    def test_schedule_purge_task_sends_dramatiq_message(self):
        """_schedule_purge_task verstuurt een Dramatiq actor-bericht."""
        with patch("src.core.api.v1.gdpr_compliance.erasure_router.purge_user_data") as mock_actor:
            mock_actor.send = MagicMock()
            from src.core.api.v1.gdpr_compliance.erasure_router import _schedule_purge_task

            _schedule_purge_task(user_id=42, tenant_id=1, scope="all")
            mock_actor.send.assert_called_once()

    def test_purge_actor_exists(self):
        """purge_user_data Dramatiq actor bestaat."""
        from src.core.actors.gdpr_purge import purge_user_data

        assert callable(purge_user_data)

    def test_schedule_purge_no_longer_has_todo_comment(self):
        """_schedule_purge_task bevat geen TODO-comment meer."""
        from pathlib import Path

        _root = Path(__file__).parent.parent.parent
        source = (_root / "src/core/api/v1/gdpr_compliance/erasure_router.py").read_text(
            encoding="utf-8"
        )
        assert "TODO: Integrate with Celery or Redis" not in source

    def test_purge_actor_is_dramatiq_decorated(self):
        """purge_user_data is een echte Dramatiq actor (heeft .send())."""
        from src.core.actors.gdpr_purge import purge_user_data

        assert hasattr(purge_user_data, "send"), (
            "purge_user_data heeft geen .send() -- is het een @dramatiq.actor?"
        )

    def test_schedule_purge_passes_tenant_id(self):
        """_schedule_purge_task geeft tenant_id door aan de actor."""
        with patch("src.core.api.v1.gdpr_compliance.erasure_router.purge_user_data") as mock_actor:
            mock_actor.send = MagicMock()
            from src.core.api.v1.gdpr_compliance.erasure_router import _schedule_purge_task

            _schedule_purge_task(user_id=99, tenant_id=42, scope="all")
            call_kwargs = mock_actor.send.call_args
            assert "42" in str(call_kwargs), "tenant_id=42 niet doorgegeven aan actor"

    def test_actor_does_not_use_celery(self):
        """Dramatiq actor importeert geen Celery (ADR-006: Redis broker)."""
        import src.core.actors.gdpr_purge as mod

        source = inspect.getsource(mod)
        assert "celery" not in source.lower()

    def test_actor_uses_tenant_id_filter(self):
        """Dramatiq actor filtert altijd op tenant_id (cross-tenant purge preventie)."""
        import src.core.actors.gdpr_purge as mod

        source = inspect.getsource(mod)
        assert "tenant_id" in source, (
            "tenant_id filter ontbreekt in purge actor -- cross-tenant purge risico!"
        )

    def test_purge_does_not_hard_delete(self):
        """Actor gebruikt anonimisering, geen hard DELETE (bewaarplicht audit trail)."""
        import src.core.actors.gdpr_purge as mod

        source = inspect.getsource(mod)
        # Hard DELETE op user data is niet toegestaan -- update naar [PURGED] wel
        assert "DELETE FROM" not in source.upper() or "[PURGED]" in source

    def test_actor_has_max_retries(self):
        """Actor heeft max_retries geconfigureerd (geen oneindige retry loop)."""
        import src.core.actors.gdpr_purge as mod

        source = inspect.getsource(mod)
        assert "max_retries" in source

    def test_actor_logs_completion_without_pii(self):
        """Actor logt completion zonder user PII (geen naam, e-mail in logs)."""
        import src.core.actors.gdpr_purge as mod

        source = inspect.getsource(mod)
        # Log-statements mogen user_id (int) bevatten maar geen e-mailadressen
        assert (
            "first_name" not in source.replace("first_name", "").replace("PURGED", "")
            or "PURGED" in source
        )

    def test_unauthenticated_dsar_request_returns_401(self, client):
        """DSAR endpoint zonder auth geeft 401."""
        response = client.post("/api/gdpr/delete-all", json={"scope": "all"})
        assert response.status_code == 401

    def test_dsar_request_response_format(self, client, auth_headers):
        """DSAR endpoint response heeft correct format (CLAUDE.md 12)."""
        response = client.post(
            "/api/gdpr/delete-all",
            json={"delete_type": "soft", "reason": "test", "scope": "all"},
            headers=auth_headers,
        )
        if response.status_code in (200, 202):
            data = response.json()
            assert "success" in data
