"""Company Layer API - v1

This module provides API endpoints for company and department management.
"""

from typing import Any

from src.core.api.v1.company.department_router import router as department_router
from src.core.api.v1.company.router import router as company_router

__all__ = ["company_router", "department_router"]
