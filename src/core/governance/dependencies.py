"""GDPR governance Depends factories (ADR-033 facade layer, SP-DLP-002 Dag 2).

Single source of the pre-configured LawfulBasisRegistry.
Domain dependencies.py files re-export get_lawful_basis_registry; routers
never import directly from src.core.governance.*.
"""

import logging

from src.core.governance.lawful_basis_registry import (
    LawfulBasis,
    LawfulBasisMissingError,
    LawfulBasisRegistry,
)

logger = logging.getLogger(__name__)

_ENDPOINT_CONSENT_STATUS = "/api/v1/privacy/consent-status"
_ENDPOINT_CONSENT_UPDATE = "/api/v1/privacy/consent"
_ENDPOINT_CONSENT_WITHDRAW = "/api/v1/privacy/consent/withdraw"
_ENDPOINT_PORTABILITY_EXPORT = "/api/gdpr/export"
_ENDPOINT_ACCESS_TRAIL = "/api/gdpr/audit-trail"


def _build_registry() -> LawfulBasisRegistry:
    registry = LawfulBasisRegistry()
    registry.register_endpoint(
        endpoint=_ENDPOINT_CONSENT_STATUS,
        lawful_basis=LawfulBasis.CONSENT,
        data_categories=["consent_preferences"],
        purpose="Read GDPR Art. 7 consent status",
    )
    registry.register_endpoint(
        endpoint=_ENDPOINT_CONSENT_UPDATE,
        lawful_basis=LawfulBasis.CONSENT,
        data_categories=["consent_preferences"],
        purpose="Update GDPR Art. 7 consent preferences",
    )
    registry.register_endpoint(
        endpoint=_ENDPOINT_CONSENT_WITHDRAW,
        lawful_basis=LawfulBasis.CONSENT,
        data_categories=["consent_preferences"],
        purpose="Withdraw GDPR Art. 7(3) consent",
    )
    registry.register_endpoint(
        endpoint=_ENDPOINT_PORTABILITY_EXPORT,
        lawful_basis=LawfulBasis.CONTRACT,
        data_categories=["personal", "agents", "tasks", "workflows", "audit"],
        purpose="GDPR Art. 20 right to data portability",
    )
    registry.register_endpoint(
        endpoint=_ENDPOINT_ACCESS_TRAIL,
        lawful_basis=LawfulBasis.LEGAL_OBLIGATION,
        data_categories=["audit_logs"],
        purpose="GDPR Art. 15 right of access to personal data",
    )
    return registry


_registry: LawfulBasisRegistry = _build_registry()


def get_lawful_basis_registry() -> LawfulBasisRegistry:
    """FastAPI dependency: returns the pre-configured LawfulBasisRegistry singleton."""
    return _registry


__all__ = [
    "LawfulBasisMissingError",
    "LawfulBasisRegistry",
    "get_lawful_basis_registry",
]
