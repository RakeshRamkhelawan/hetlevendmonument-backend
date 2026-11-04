"""Sentiment Scanner domain package (ADR-033 Laag 2).

Replicates the legacy double-prefix behaviour:
  registries/agents.py adds /api/v1/agents at Laag 3 (preserved as pre-existing behaviour).
  scanner_router retains /api/v1/sentiment-scanner as its own prefix.
Combined routes land at /api/v1/agents/api/v1/sentiment-scanner/... (pre-existing, unchanged).

# TODO(SP-VOLGENDE): dubbele prefix is een bug -- routes zouden op /api/v1/sentiment-scanner/
# moeten staan (niet genest onder /agents). Fix vereist URL-migratie voor bestaande clients.
"""

from fastapi import APIRouter

from .router import router as ss_composite_router

domain_router = APIRouter(prefix="/api/v1/agents", tags=["Sentiment"])
domain_router.include_router(ss_composite_router)

__all__ = ["domain_router"]
