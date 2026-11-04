"""
Analytics API - cross-company benchmarking endpoints and the ROI of the own tenant.

Benchmarking provides privacy-preserving data for pack usage across companies with k-anonymity
guarantees. The ROI router (`roi.py`) lives in this package because the registry mounts exactly
this `router`; a sibling module `analytics.py` was shadowed by this package and never loaded
(measured 2026-10-10), so a route placed there is not served.
"""

from fastapi import APIRouter

from src.core.api.v1.analytics.benchmarks import router as benchmarks_router
from src.core.api.v1.analytics.roi import router as roi_router

router = APIRouter()
router.include_router(benchmarks_router)
router.include_router(roi_router)

__all__ = ["router"]
