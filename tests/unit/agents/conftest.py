"""Fixtures voor de agent-unittests.

Deze tests roepen `BaseSpecialistAgent.act()` rechtstreeks aan. Sinds BE-AGT-041, BE-AGT-042
en ADR-036 OP-163 raakt dat pad drie governance-lagen die een databaseverbinding openen, dus
dezelfde stubs als in `tests/unit/als/conftest.py` gelden hier ook.
"""

from tests.fixtures.agent_governance import (  # noqa: F401
    council_gate,
    hitl_ticket_repository,
    prana_guard,
)
