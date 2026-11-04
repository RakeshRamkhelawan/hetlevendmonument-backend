"""
Council members (Officers).

Each Officer is responsible for one aspect of governance and produces a
single OfficerVerdict per Proposal. All Officers implement the Officer
abstract base class.

The seven Officers (in their deliberation order):
    1. ComplianceOfficer  - EU AI Act, GDPR, ISO 42001 compliance
    2. PrivacyOfficer     - PII, consent, cross-session memory
    3. SecurityOfficer    - Tool allowlist, prompt injection, scopes
    4. RiskOfficer        - Impact, HITL escalation, Shadow CEO veto
    5. EthicsOfficer      - Bias, fairness, transparency
    6. ResourceOfficer    - Budgets, rate limits, notification budget
    7. AuditOfficer       - Persists decision to hash chain (always last)

Officers 1-6 deliberate in parallel (asyncio.gather). AuditOfficer runs
after the aggregation step and is the only Officer that can fail the
final write (fail-secure).
"""

from __future__ import annotations

from src.core.copilot.council.members.audit_officer import AuditOfficer
from src.core.copilot.council.members.base import Officer
from src.core.copilot.council.members.compliance_officer import ComplianceOfficer
from src.core.copilot.council.members.ethics_officer import EthicsOfficer
from src.core.copilot.council.members.privacy_officer import PrivacyOfficer
from src.core.copilot.council.members.resource_officer import ResourceOfficer
from src.core.copilot.council.members.risk_officer import RiskOfficer
from src.core.copilot.council.members.sanity_officer import SanityOfficer
from src.core.copilot.council.members.security_officer import SecurityOfficer

__all__ = [
    "Officer",
    "ComplianceOfficer",
    "PrivacyOfficer",
    "SecurityOfficer",
    "RiskOfficer",
    "EthicsOfficer",
    "ResourceOfficer",
    "AuditOfficer",
    "SanityOfficer",
]
