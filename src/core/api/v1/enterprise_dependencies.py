"""Enterprise domain dependencies (ADR-033 Laag 1).

Centraliseert de forbidden import uit enterprise.py zodat het router-bestand
zelf geen directe als-import meer heeft.
"""

from src.core.als.agents.loader import (
    DomainPack as DomainPack,
    EnterpriseCatalogLoader as EnterpriseCatalogLoader,
)

__all__ = [
    "DomainPack",
    "EnterpriseCatalogLoader",
]
