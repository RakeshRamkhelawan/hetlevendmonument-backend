# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Workflow visualization sub-router (SP-API-003 Dag 2).

Routes:
    GET  /api/v1/workflows/visual/sops/{sop_id}
    POST /api/v1/workflows/visual/sops/{sop_id}
"""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from .dependencies import visualizer

router = APIRouter(prefix="/api/v1/workflows/visual", tags=["workflow-visualization"])
logger = logging.getLogger(__name__)

SOP_DIR = Path("src/core/knowledge/sops/definitions")


@router.get("/sops/{sop_id}", response_model=dict[str, Any])
async def get_sop_visualization(
    sop_id: str,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get the React Flow JSON representation of a SOP."""
    import yaml

    normalized_request = sop_id.lower().replace("-", "_").replace(" ", "_")

    file_path = None
    for f in SOP_DIR.glob("*.yaml"):
        try:
            content = f.read_text(encoding="utf-8")
            parsed = yaml.safe_load(content)

            if parsed and isinstance(parsed, dict):
                file_id = parsed.get("id", "")
                if file_id and file_id.lower() == sop_id.lower():
                    file_path = f
                    break

                normalized_file_id = file_id.lower().replace("-", "_").replace(" ", "_")
                if normalized_file_id == normalized_request:
                    file_path = f
                    break

            normalized_filename = f.stem.lower().replace("-", "_")
            if normalized_filename == normalized_request:
                file_path = f
                break

        except Exception as e:
            logger.warning("Error parsing %s: %s: %s", f.name, type(e).__name__, e)
            continue

    if not file_path:
        available = [f.stem for f in SOP_DIR.glob("*.yaml")]
        raise HTTPException(
            status_code=404,
            detail="SOP '%s' not found. Available: %s" % (sop_id, available),
        )

    try:
        content = file_path.read_text(encoding="utf-8")
        return visualizer.yaml_to_flow(content)
    except Exception as e:
        logger.error("Error visualizing SOP: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to visualize SOP") from e


@router.post("/sops/{sop_id}")
async def save_sop_visualization(
    sop_id: str,
    flow_data: dict[str, Any] = Body(...),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Convert React Flow JSON back to YAML and save."""
    try:
        yaml_content = visualizer.flow_to_yaml(flow_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid Flow Data") from e

    file_path = None
    for f in SOP_DIR.glob("*.yaml"):
        if sop_id.lower() in f.name.lower():
            file_path = f
            break

    if not file_path:
        file_path = SOP_DIR / ("%s.yaml" % sop_id.lower().replace(" ", "_"))

    try:
        file_path.write_text(yaml_content, encoding="utf-8")
        return {"success": True, "message": "SOP %s updated." % sop_id}
    except Exception as e:
        logger.error("Error saving SOP: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to write file") from e
