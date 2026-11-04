import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from src.core.api.v1.workflow.workflow_visualization_router import (
    router,
    get_sop_visualization,
    save_sop_visualization,
)


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/api/v1/workflows/visual/sops/{sop_id}" in paths


@pytest.mark.asyncio
async def test_get_sop_visualization_not_found() -> None:
    with patch("src.core.api.v1.workflow.workflow_visualization_router.SOP_DIR") as mock_dir:
        mock_dir.glob.return_value = []
        with pytest.raises(HTTPException) as exc_info:
            await get_sop_visualization(sop_id="nonexistent_sop")
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_sop_visualization_success() -> None:
    mock_file = MagicMock(spec=Path)
    mock_file.read_text.return_value = "id: my_sop\nname: Test SOP\n"
    mock_file.stem = "my_sop"

    with patch("src.core.api.v1.workflow.workflow_visualization_router.SOP_DIR") as mock_dir, \
         patch("src.core.api.v1.workflow.workflow_visualization_router.visualizer") as mock_vis:
        mock_dir.glob.return_value = [mock_file]
        mock_vis.yaml_to_flow.return_value = {"nodes": [], "edges": []}

        res = await get_sop_visualization(sop_id="my_sop")
        assert res == {"nodes": [], "edges": []}


@pytest.mark.asyncio
async def test_save_sop_visualization_success() -> None:
    mock_file = MagicMock(spec=Path)
    mock_file.name = "my_sop.yaml"

    with patch("src.core.api.v1.workflow.workflow_visualization_router.SOP_DIR") as mock_dir, \
         patch("src.core.api.v1.workflow.workflow_visualization_router.visualizer") as mock_vis:
        mock_dir.glob.return_value = [mock_file]
        mock_vis.flow_to_yaml.return_value = "id: my_sop\n"

        res = await save_sop_visualization(sop_id="my_sop", flow_data={"nodes": []})
        assert res["success"] is True
        assert "updated" in res["message"]
        mock_file.write_text.assert_called_once_with("id: my_sop\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_save_sop_visualization_invalid_data() -> None:
    with patch("src.core.api.v1.workflow.workflow_visualization_router.visualizer") as mock_vis:
        mock_vis.flow_to_yaml.side_effect = ValueError("Corrupt graph")

        with pytest.raises(HTTPException) as exc_info:
            await save_sop_visualization(sop_id="my_sop", flow_data={})
        assert exc_info.value.status_code == 400
        assert "Invalid Flow Data" in exc_info.value.detail
