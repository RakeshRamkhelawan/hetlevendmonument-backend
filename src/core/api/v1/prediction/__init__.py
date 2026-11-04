"""Prediction domain package (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .router import router as prediction_composite_router

domain_router = APIRouter(tags=["Phase5-Prediction"])
domain_router.include_router(prediction_composite_router)

__all__ = ["domain_router"]
