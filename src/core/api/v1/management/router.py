"""Management composite router -- assembles all sub-routers."""

from fastapi import APIRouter

from .agents_router import router as agents_router
from .logs_router import router as logs_router
from .tasks_router import router as tasks_router

router = APIRouter()
router.include_router(agents_router)
router.include_router(tasks_router)
router.include_router(logs_router)
