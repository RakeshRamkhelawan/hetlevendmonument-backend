from typing import Any, Dict, List  # TODO(TYPE): replace Any with concrete type
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)

from fastapi import APIRouter, HTTPException

from src.core.api.v1.enterprise_dependencies import DomainPack, EnterpriseCatalogLoader

router = APIRouter(prefix="/enterprise", tags=["Enterprise"])


@router.get("/catalog/packs")
async def list_domain_packs() -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Lists all available domain packs in the enterprise catalog."""
    loader = EnterpriseCatalogLoader()
    # Ensure loaded
    loader.load_all()

    return [
        {
            "id": p.pack_id,
            "name": p.name,
            "step_count": len(p.steps),
            "agents": [s.agent_id for s in p.steps],
        }
        for p in loader.packs.values()
    ]


@router.get("/catalog/packs/{pack_id}")
async def get_pack_details(pack_id: str) -> DomainPack:
    loader = EnterpriseCatalogLoader()
    loader.load_all()
    pack = loader.packs.get(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    return pack
