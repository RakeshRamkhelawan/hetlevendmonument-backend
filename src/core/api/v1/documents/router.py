"""Document Management API router composite (ADR-033 Laag 2).

SP-API-002 Dag 4: gesplitst in 4 Laag-1 sub-routers.
Originele monolithische router vervangen door composite.
"""

from fastapi import APIRouter

from src.core.api.v1.documents.crud_router import crud_router
from src.core.api.v1.documents.processing_router import processing_router
from src.core.api.v1.documents.search_router import search_router
from src.core.api.v1.documents.upload_router import upload_router

router = APIRouter(prefix="/documents", tags=["Document Management"])

router.include_router(upload_router)
router.include_router(search_router)
router.include_router(processing_router)
# NOTE: crud_router last -- its /{doc_id} catch-all must not shadow /search or /{doc_id}/process
router.include_router(crud_router)
