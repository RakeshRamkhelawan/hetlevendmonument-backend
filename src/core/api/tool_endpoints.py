# orphan:exempt reason: SP-API-010 proxy stub -- TODO(SP-API-011): migreer naar v1/tools/
from typing import Any

from fastapi import APIRouter, Response

from src.core.activepieces.catalog_syncer import catalog_syncer

router = APIRouter()


@router.get(
    "/integrations/catalog",
    deprecated=True,
    response_model=list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
)
async def get_tool_catalog(
    response: Response,
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Returns the full catalog of ActivePieces integrations.

    Deprecated: use v1/tools/ when available (SP-API-011).
    """
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Thu, 01 Jan 2028 00:00:00 GMT"
    # TODO(SP-API-011): geen v1/tools/ route voor /integrations/catalog -- aanmaken in SP-API-011
    catalog = catalog_syncer.load_catalog()
    if not catalog:
        catalog = await catalog_syncer.sync_all()
    return catalog


@router.get(
    "/integrations/search",
    deprecated=True,
    response_model=list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
)
async def search_tools(
    q: str, response: Response
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Semantic search for tools.

    Deprecated: use v1/tools/ when available (SP-API-011).
    """
    del q  # proxy stub -- parameter bewaard voor API-compatibiliteit
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Thu, 01 Jan 2028 00:00:00 GMT"
    # TODO(SP-API-011): geen v1/tools/ route voor /integrations/search -- aanmaken in SP-API-011
    # tool_advisor (src.core.agents.*) verwijderd -- verboden import ADR-033 Contract 2
    return []
