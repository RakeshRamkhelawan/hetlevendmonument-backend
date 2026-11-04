"""Contracts domain dependencies (ADR-033 Laag 1).

Centraliseert de forbidden import uit contracts.py zodat het router-bestand
zelf geen directe als-import meer heeft.
"""

from src.core.als.enterprise.departments.department_orchestrator import Department as Department

__all__ = [
    "Department",
]
