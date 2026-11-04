import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.core.api.v1.canvas.canvas_templates_router import (
    canvas_templates_router,
    list_templates,
    create_from_template,
)
from src.domains.canvas.service import CanvasService


def test_routes_registered() -> None:
    paths = [r.path for r in canvas_templates_router.routes]
    assert "/templates/list" in paths
    assert "/from-template/{template_id}" in paths


@pytest.mark.asyncio
async def test_list_templates() -> None:
    res = await list_templates()
    assert len(res) == 4
    template_ids = [t["id"] for t in res]
    assert "blank" in template_ids
    assert "strategy" in template_ids
    assert "workflow" in template_ids
    assert "dashboard" in template_ids


@pytest.mark.asyncio
async def test_create_from_template_success() -> None:
    mock_service = MagicMock(spec=CanvasService)
    canvas_id = uuid4()
    mock_canvas = {
        "id": canvas_id,
        "name": "My Canvas",
        "template": "strategy",
        "is_public": False,
        "tenant_id": uuid4(),
        "owner_id": uuid4(),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "version": 1,
        "blocks": [],
        "connections": [],
        "collaborators": [],
    }
    mock_service.create_canvas = AsyncMock(return_value=mock_canvas)

    res = await create_from_template(
        template_id="strategy",
        name="My Canvas",
        service=mock_service,
    )
    assert res.id == canvas_id
    assert res.name == "My Canvas"
    assert res.template == "strategy"
    mock_service.create_canvas.assert_awaited_once()
