"""Gatekeeper API v1 module.

Provides endpoints for:
- Listing and querying Gatekeeper decisions
- HITL (Human-in-the-Loop) approval workflows
- Chain verification and integrity checks
- Statistics and metrics

ADR-017: Deterministic policy enforcement
ADR-005: Tenant isolation via JWT
"""

from src.core.api.v1.gatekeeper.router import router

__all__ = ["router"]
