"""Gedeelde stubs voor de governance-lagen die een skill-uitvoering aanroept.

Drie lagen openen een echte databaseverbinding zodra `act()` of een uitvoerpad draait:

  - `PranaGuard.check_budget()` (`governance/prana_guard.py:25`), sinds BE-AGT-041 op beide
    uitvoerpaden;
  - `request_council_decision_for_agent()` (`copilot/council/background_gate.py:93`), sinds
    BE-AGT-042 per tool-call;
  - `HITLTicketRepository.create_hitl_request()` (`tool_broker/hitl_repository.py:432`), sinds
    ADR-036 OP-163 op het HITL_REQUIRED-pad van `_council_rejection()`.

Een unittest hoort geen databaseverbinding te openen. Zonder stub kost dat in het gunstige
geval een directe `RuntimeError: Database not initialized`, en in het ongunstige geval vijf
retries met backoff -- gemeten 28 seconden per test toen dit bij `CritiqueStore` gebeurde
(OP-18). Precies dit trof `test_council_gate_per_action.py`'s HITL_REQUIRED-parametercase
opnieuw bij het bouwen van OP-163, tot deze derde stub erbij kwam.

**`hitl_ticket_repository` is met opzet GEEN autouse, anders dan de eerste twee.** Hij patcht
`get_db_session` op de bron -- een generieke, breed gedeelde infrastructuurfunctie, niet een
governance-specifieke naam zoals de eerste twee. Autouse zou daarom ELKE test in de drie
testbomen raken, ook tests die met HITL niets te maken hebben. Gemeten in de Gate 2-review
(2026-08-18): met autouse faalde
`test_agent_router_discovery_wiring.py::test_dependencies_get_master_orchestrator_wires_async_session_factory`,
die een verse import doet en met `is` tegen de ECHTE functie vergelijkt. Alleen de tests die
het HITL_REQUIRED-pad daadwerkelijk raken vragen hem expliciet op (vandaag zes, uitsluitend
in `test_council_gate_per_action.py` -- geen vast getal hier noemen: dat liep al eens stil uit
de pas toen dit aantal groeide, zie M-3 in de blinde review van 2026-08-19).

Hier gebundeld en niet per testmap gekopieerd: het gaat om dezelfde lagen, en een kopie per
map loopt uiteen zodra er een laag bijkomt. Conftests halen ze op met:

    from tests.fixtures.agent_governance import (  # noqa: F401
        council_gate,
        hitl_ticket_repository,
        prana_guard,
    )
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def prana_guard() -> Any:
    """Stub `PranaGuard`; yields de instantie zodat een test op de aanroepen kan asserteren."""
    with patch("src.core.governance.prana_guard.PranaGuard") as guard_cls:
        instance = AsyncMock()
        instance.check_budget = AsyncMock(return_value=None)
        instance.charge_prana = AsyncMock(return_value=None)
        guard_cls.return_value = instance
        yield instance


@pytest.fixture(autouse=True)
def council_gate() -> Any:
    """Stub de Council-ingang.

    Gepatcht op de plek waar `specialist_base` hem IMPORTEERT en niet waar hij is
    gedefinieerd: een `from ... import naam` bindt de functie aan de importerende module, dus
    patchen bij de bron heeft geen effect meer zodra die import is uitgevoerd.

    Default-verdict APPROVED, zodat tests die niets met de Council te maken hebben er niet
    door gehinderd worden; tests die verdict-gedrag onderzoeken zetten `return_value` zelf.

    **Bewust risico, benoemd in de Gate 2-review (BE-AGT-043).** Deze fixture is autouse in
    drie testbomen (`tests/unit/als`, `tests/unit/agents`, `tests/unit/tool_broker`) en geeft
    standaard APPROVED. Gevolg: het verwijderen van de Council-poort uit `act()` maakt in die
    bomen GEEN enkele test rood -- de stub blijft immers gewoon antwoorden. Het alternatief
    (opt-in) is afgewogen en niet gekozen: zonder stub opent elke skill-uitvoering een echte
    databaseverbinding, met vijf verbindingspogingen en backoff tegen een suite-timeout van
    60 seconden (OP-18: dat kostte eerder 56,8s per test).

    Wat het gat dekt: `tests/architecture/test_agent_actions_pass_council.py`. Die guard is
    hier het ENIGE vangnet op de aanwezigheid van de poort en is mutatie-getest. Sloop die
    guard niet zonder deze fixture eerst opt-in te maken.

    `decision_id` staat erop sinds ADR-036 D4-002: de piloot-skill (het meest gebruikte
    testvehikel in de drie testbomen hierboven) is Annex III/HITL, dus een APPROVED-verdict
    floort voor die skill altijd door naar `_council_rejection()`'s HITL_REQUIRED-tak, en die
    tak leest `decision.decision_id`. Zonder dit veld faalt elke piloot-test met deze default
    op een `AttributeError`, niet op het scenario die hij zelf test.
    """
    from src.core.copilot.council.background_gate import AgentCouncilOutcome
    from src.core.copilot.council.types import DecisionVerdict

    class _ApprovedDecision:
        verdict = DecisionVerdict.APPROVED
        explanation_for_user = "stub: goedgekeurd"
        decision_id = "decision-stub-approved"

    with patch(
        "src.core.als.agents.specialist_base.request_council_decision_for_agent",
        new_callable=AsyncMock,
    ) as gate:
        # `hitl_ticket_ref=None` klopt hier altijd: het RAUWE verdict is APPROVED, dus de
        # (gemockte) gate zou zelf geen ticket hebben aangemaakt (ADR-036 OP-167). Floort de
        # D4-002-floor dit alsnog naar HITL_REQUIRED voor de piloot-skill, dan maakt
        # `_council_rejection()` zelf een ticket aan -- ongewijzigd gedrag, zie
        # `hitl_ticket_repository` hieronder.
        gate.return_value = AgentCouncilOutcome(
            decision=_ApprovedDecision(),  # type: ignore[arg-type]
            hitl_ticket_ref=None,
        )
        yield gate


@pytest.fixture
def hitl_ticket_repository() -> Any:
    """Stub de ticketaanmaak op het HITL_REQUIRED-pad (ADR-036 OP-163).

    Gepatcht op de BRON (`src.core.database.session` / `src.core.tool_broker.hitl_repository`),
    niet op de plek waar `specialist_base` importeert -- want dat doet hij niet meer statisch.
    `_council_rejection()` haalt beide modules op via `importlib.import_module(...)` in plaats
    van een top-level `from ... import ...`: een statische import telt als eigen STATEMENT mee
    in `test_agent_runtime_ce_dag2_final_target`'s Ce-ceiling voor `agent_runtime` (225,
    `unique_pairs=False` in `scan_module` -- elke `ast.ImportFrom` telt, ook als de bucket al
    door een andere import wordt aangesproken). Twee statische imports duwden Ce naar 227;
    `importlib` voor beide bracht hem terug naar 225. Omdat `importlib.import_module` de module
    telkens vers uit `sys.modules` haalt, werkt patchen op de bron hier wel -- dezelfde reden
    waarom `__init__` hierboven al `database.database` zo importeert (specialist_base.py:109).

    **Bewust NIET autouse (in tegenstelling tot `council_gate`/`prana_guard` hierboven).**
    `get_db_session` is een generieke, breed gedeelde infrastructuurfunctie -- patchen op de bron
    raakt (in autouse-vorm) ELKE test in de drie testbomen die deze module importeren, ook tests
    die met HITL niets te maken hebben. Gemeten door de Gate 2-code-review (2026-08-18): met
    autouse faalde `tests/unit/agents/test_agent_router_discovery_wiring.py::
    test_dependencies_get_master_orchestrator_wires_async_session_factory`, die een VERSE
    `from src.core.database.session import get_db_session` doet en met `is` tegen de ECHTE
    functie vergelijkt -- die identiteitscontrole zag toen de nep-functie van deze fixture.
    Bevestigd zelf gereproduceerd (rood met autouse, groen zonder). Alleen de tests die het
    HITL_REQUIRED-pad daadwerkelijk raken (uitsluitend in `test_council_gate_per_action.py`)
    vragen hem op -- geen vast getal hier noemen, zie de docstring hierboven bij dit bestand.

    Yields de repository-dubbel, zodat een test kan asserteren MET welke argumenten
    (`executing_identity`, `action_type`, ...) het ticket is aangevraagd -- net als
    `council_gate` een dubbel yield't in plaats van alleen te stubben.
    """
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_db_session() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()

    instance = AsyncMock()
    instance.create_hitl_request = AsyncMock(return_value="TICKET-STUB-OP163")

    with (
        patch("src.core.database.session.get_db_session", _fake_db_session),
        patch(
            "src.core.tool_broker.hitl_repository.HITLTicketRepository",
            return_value=instance,
        ),
    ):
        yield instance
