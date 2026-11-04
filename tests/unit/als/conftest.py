"""Gedeelde fixtures voor de ALS-unittests.

De governance-stubs staan in `tests/fixtures/agent_governance.py` en worden hier
geherexporteerd. Ze zijn autouse, want zonder stub opent elke skill-uitvoering een echte
databaseverbinding -- zie de uitleg in dat bestand.

`tests/unit/agents/conftest.py` importeert dezelfde drie, omdat `act()` daar rechtstreeks
wordt aangeroepen.
"""

from tests.fixtures.agent_governance import (  # noqa: F401
    council_gate,
    hitl_ticket_repository,
    prana_guard,
)
