# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
"""
Search API Endpoints

Provides hybrid search combining vector and BM25 retrieval.
"""

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.api.schemas.search_schemas import (
    HybridSearchRequest,
    HybridSearchResponse,
    SearchMetadata,
    SearchResultItem,
    SearchSource,
)
from src.core.middleware.tenant_context import require_tenant_id
from src.core.search.hybrid_search import HybridSearchConfig, hybrid_search

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


async def get_current_tenant_id() -> int:
    """Dependency to get current tenant ID from request context"""
    return require_tenant_id()


@router.post("/hybrid", response_model=HybridSearchResponse)
async def search_hybrid(
    request: HybridSearchRequest, tenant_id: int = Depends(get_current_tenant_id)
) -> HybridSearchResponse:
    """
    Perform hybrid search combining vector and BM25 retrieval

    - **query**: Search query string
    - **top_k**: Number of results to return (1-100)
    - **fusion_method**: 'rrf' or 'weighted'
    - **alpha**: Balance between vector (1.0) and BM25 (0.0)
    """
    logger.info(f"Hybrid search: tenant={tenant_id}, query='{request.query}'")
    start_time = time.perf_counter()

    try:
        config = HybridSearchConfig(
            fusion_method=request.fusion_method.value,
            alpha=request.alpha,
            rrf_k=request.rrf_k,
        )
        config.validate()

        results = await hybrid_search(
            tenant_id=tenant_id, query=request.query, top_k=request.top_k, config=config
        )

        execution_time = (time.perf_counter() - start_time) * 1000

        # Map results to response model
        response_items: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for i, r in enumerate(results):
            # Determine source enum
            try:
                source_enum = SearchSource(r.source)
            except ValueError:
                source_enum = SearchSource.BOTH

            content: str | None = r.content
            if request.include_content and len(content or "") > request.max_content_length:
                content = (content or "")[: request.max_content_length] + "..."
            elif not request.include_content:
                content = None

            response_items.append(
                SearchResultItem(
                    document_id=r.document_id,
                    content=content,
                    metadata=r.metadata,
                    vector_score=r.vector_score,
                    bm25_score=r.bm25_score,
                    hybrid_score=r.hybrid_score,
                    source=source_enum,
                    rank=i + 1,
                )
            )

        return HybridSearchResponse(
            results=response_items,
            total_results=len(results),
            metadata=SearchMetadata(
                query=request.query,
                tenant_id=tenant_id,
                fusion_method=request.fusion_method.value,
                alpha=request.alpha,
                execution_time_ms=execution_time,
                vector_results_count=0,  # Placeholder, hybrid_search doesn't return counts yet
                bm25_results_count=0,
            ),
        )

    except ValueError as e:
        logger.error("search_hybrid mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=400, detail="Ongeldig verzoek.")
    except RuntimeError as e:
        # Both search engines failed
        logger.error(f"Hybrid search service unavailable: {e}")
        raise HTTPException(status_code=503, detail="Search service temporarily unavailable")
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/hybrid", response_model=HybridSearchResponse)
async def search_hybrid_get(
    query: str = Query(..., min_length=1, max_length=500),
    top_k: int = Query(10, ge=1, le=100),
    fusion_method: str = Query("rrf"),
    tenant_id: int = Depends(get_current_tenant_id),
) -> HybridSearchResponse:
    """GET version of hybrid search for simple queries"""
    # Map string to enum manually since Query param is string
    from src.core.api.schemas.search_schemas import FusionMethod

    try:
        method = FusionMethod(fusion_method)
    except ValueError:
        method = FusionMethod.RRF

    request = HybridSearchRequest(query=query, top_k=top_k, fusion_method=method)
    return await search_hybrid(request, tenant_id)
