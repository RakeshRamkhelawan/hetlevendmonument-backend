"""Unit tests for cva_tasks tenant context cleanup.

Regression test for AUDIT-003: if CVA message processing fails after the tenant
ContextVar is set, set_tenant_id(None) must still run so a pooled Dramatiq thread
does not keep the previous tenant_id.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.tasks.cva_tasks import process_cva_message


@pytest.mark.unit
def test_cleanup_runs_when_cva_processing_fails() -> None:
    """When processing raises after tenant is set, tenant ContextVar must be cleared."""
    tenant_id = 43
    request_data: dict[str, object] = {
        "tenant_id": tenant_id,
        "channel": "telegram",
        "text": "hello",
        "sender_id": "12345",
    }
    cleanup_calls: list[object] = []

    def fake_set_tenant_id(value: object) -> None:
        cleanup_calls.append(value)

    with (
        patch("src.core.tasks.cva_tasks.set_tenant_id", side_effect=fake_set_tenant_id),
        patch(
            "src.core.tasks.cva_tasks.db_manager.initialize",
            side_effect=RuntimeError("db init failed"),
        ),
    ):
        with pytest.raises(RuntimeError, match="db init failed"):
            process_cva_message(request_data)

    assert cleanup_calls == [tenant_id, None]
