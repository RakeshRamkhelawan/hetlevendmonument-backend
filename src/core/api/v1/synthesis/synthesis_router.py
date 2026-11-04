"""
Synthesis sub-router (ADR-033 Laag 1).

Thin delivery layer -- delegates all logic to helper functions.
Route: POST /synthesis
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import require_scopes, OAuth2Scope

from .dependencies import get_tenant
from .synthesis_service import (
    SynthesisRequest,
    SynthesisResponse,
    SynthesisResult,
    SynthesisMetrics,
    generate_synthesis_content,
    generate_source_citations,
    get_user_id,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


@router.post(
    "/synthesis",
    response_model=SynthesisResponse,
    summary="Generate synthesis from documents",
    description="Generates a synthesis from one or more document sources.",
)
async def generate_synthesis(
    request: SynthesisRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: dict[str, Any] = Depends(require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),  # TODO(TYPE): replace Any with concrete type
) -> SynthesisResponse:
    """
    Generate synthesis from documents.

    Supports multiple synthesis types:
    - **summary**: Condensed summary of documents
    - **analysis**: Detailed analysis with insights
    - **comparison**: Side-by-side comparison
    - **extraction**: Entity and fact extraction
    - **translation**: Translation to target language

    Security: Requires JWT with workflows:write scope
    """
    user_id = get_user_id(current_user)
    now = datetime.now(timezone.utc)
    synthesis_id = f"synth_{uuid.uuid4().hex[:12]}"
    start_time = now

    logger.info(
        "Generating synthesis",
        extra={
            "synthesis_id": synthesis_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "synthesis_type": request.synthesis_type,
            "document_count": len(request.documents),
        },
    )

    content = generate_synthesis_content(
        documents=request.documents,
        synthesis_type=request.synthesis_type,
        query=request.query,
        language=request.language,
        max_length=request.max_length,
    )

    sources: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    if request.include_sources:
        sources = generate_source_citations(request.documents)

    end_time = datetime.now(timezone.utc)
    processing_ms = int((end_time - start_time).total_seconds() * 1000)

    from .synthesis_service import extract_document_content

    total_input_tokens = sum(
        len(extract_document_content(doc).split()) for doc in request.documents
    )

    metrics = SynthesisMetrics(
        documents_processed=len(request.documents),
        total_tokens_input=total_input_tokens,
        total_tokens_output=len(content.split()),
        processing_time_ms=processing_ms,
        model_used="rule-based-v1",
        confidence_score=0.85,
    )

    result = SynthesisResult(
        id=synthesis_id,
        synthesis_type=request.synthesis_type,
        output_format=request.output_format,
        content=content,
        query=request.query,
        language=request.language,
        sources=sources,
        metrics=metrics,
        created_at=now.isoformat(),
        tenant_id=tenant_id,
        created_by=user_id,
    )

    logger.info(
        "Synthesis generated successfully",
        extra={
            "synthesis_id": synthesis_id,
            "content_length": len(content),
            "processing_time_ms": processing_ms,
        },
    )

    return SynthesisResponse(
        result=result,
        message=(
            f"{request.synthesis_type.value.capitalize()} generated successfully"
            f" from {len(request.documents)} document(s)"
        ),
        success=True,
    )
