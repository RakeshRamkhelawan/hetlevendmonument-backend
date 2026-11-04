"""Prediction API router composite (ADR-033 Laag 2)."""

from fastapi import APIRouter

from .prediction_router import router as prediction_sub_router

router = APIRouter()
router.include_router(prediction_sub_router)
