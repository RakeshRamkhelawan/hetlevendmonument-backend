"""CVA API router composite (ADR-033 Laag 2)."""

from fastapi import APIRouter

from src.core.api.v1.cva.chat_router import chat_router
from src.core.api.v1.cva.conversations_router import conversations_router
from src.core.api.v1.cva.legacy_router import legacy_router
from src.core.api.v1.cva.management_router import management_router
from src.core.api.v1.cva.public_router import public_router as cva_public_router

router = APIRouter()
router.include_router(chat_router)
router.include_router(legacy_router)
router.include_router(conversations_router)
router.include_router(management_router)
router.include_router(cva_public_router)
