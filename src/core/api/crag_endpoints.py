# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
"""
Corrective RAG API Endpoints
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.api.schemas.crag_schemas import CRAGRequest, CRAGResponse
from src.core.middleware.tenant_context import require_tenant_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crag", tags=["Corrective RAG"])


@router.post("/chat", response_model=CRAGResponse)
async def crag_chat(
    request: CRAGRequest, tenant_id: int = Depends(require_tenant_id)
) -> CRAGResponse:
    """
    Execute Corrective RAG workflow.

    This endpoint:
    1. Retrieves documents from hybrid search (Vector + BM25).
    2. Grades documents for relevance.
    3. If irrelevant, transforms query and searches the web (Tavily).
    4. Generates a final answer grounded in the best available context.
    """
    try:
        from src.core.agents.corrective_rag_agent import (  # lazy
            CRAGInput,
            get_corrective_rag_agent,
        )

        input_data: CRAGInput = {"query": request.query, "tenant_id": tenant_id}

        result = await get_corrective_rag_agent().ainvoke(input_data)

        return CRAGResponse(
            answer=result["answer"],
            sources=result["sources"],
            web_search_triggered=result["web_search_triggered"],
            original_query=result["original_query"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("CRAG endpoint error: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error"
        )
