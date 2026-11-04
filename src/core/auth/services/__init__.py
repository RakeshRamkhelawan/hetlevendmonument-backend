"""
Auth Services Package

Provides refactored authentication and registration services
using the BaseService dependency injection pattern.
"""

from typing import Any

from src.core.auth.services.authentication import AuthenticationService
from src.core.auth.services.registration import RegistrationService

__all__ = ["AuthenticationService", "RegistrationService"]
