"""
Semantic Router - Rajasic Layer (Layer 3)

Provides intelligent, context-aware routing using vector embeddings.
Part of the hybrid Guna routing architecture.
"""

from typing import Any

from .embedders.ollama_embedder import OllamaEmbedder
from .hybrid_router import GunaRouter
from .router import RoutingDecision, SanskritiSemanticRouter

__all__ = [
    "SanskritiSemanticRouter",
    "RoutingDecision",
    "GunaRouter",
    "OllamaEmbedder",
]
