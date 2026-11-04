"""
SQLAlchemy ORM models for the Agent Council.

CouncilDecisionRow and OfficerVerdictRow are defined in governance.models (SP-DSM-005,
ADR-027). Re-exported here for backward compatibility with callers that import from this
module. copilot -> governance is ADR-027 by design.
"""

from src.core.governance.models import CouncilDecisionRow as CouncilDecisionRow
from src.core.governance.models import OfficerVerdictRow as OfficerVerdictRow

__all__ = ["CouncilDecisionRow", "OfficerVerdictRow"]
