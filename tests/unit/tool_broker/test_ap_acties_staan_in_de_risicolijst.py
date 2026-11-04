"""Elke ActivePieces-actie heeft EEN risico, en dat staat in `tool_risk_levels.yml` (ADR-040 B12).

Brief 2026-10-20 (ActivePieces per klant, dag 1).

**Wat er stond.** `src/core/tool_broker/ap_mcp_registry.py` had een eigen enum `ToolRisk` en gaf
`gmail` en `slack` MEDIUM: loggen en achteraf een melding. Maar een mail of een bericht naar buiten
is niet terug te halen. De echte classificatie is `ToolRiskClassifier` met `tool_risk_levels.yml`;
alleen HIGH opent de mens-in-de-lus-poort (`ToolBrokerService`, ADR-015/039). Twee lijsten met
verschillende antwoorden betekent dat de zwakste wint zodra iemand de verkeerde leest.

**Wat deze tests bewaken.** De tweede lijst bestaat niet meer; elke standaardtool voor een afdeling
heeft een UITDRUKKELIJKE regel (geen terugval op de zero-trust standaard, want die zou ook een
vergeten lees-actie op HIGH zetten); uitgaande acties zijn HIGH.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.core.tool_broker import ap_mcp_registry
from src.core.tool_broker.ap_mcp_registry import DEPARTMENT_DEFAULT_TOOLS, APPiece
from src.core.tool_broker.risk_classifier import ToolRiskClassifier, ToolRiskLevel

UITGAAND = ("gmail.send_email", "slack.send_message", "google-calendar.create_event")


def _standaardtools() -> list[str]:
    return sorted({tool for tools in DEPARTMENT_DEFAULT_TOOLS.values() for tool in tools})


def test_de_tweede_risicolijst_bestaat_niet_meer() -> None:
    assert not hasattr(ap_mcp_registry, "ToolRisk")


def test_een_piece_draagt_geen_eigen_risiconiveau_meer() -> None:
    assert "risk_level" not in {f.name for f in dataclasses.fields(APPiece)}


def test_gmail_send_email_vraagt_mens_in_de_lus() -> None:
    assert ToolRiskClassifier().classify("gmail.send_email") is ToolRiskLevel.HIGH


@pytest.mark.parametrize("tool", UITGAAND)
def test_een_uitgaande_actie_is_high(tool: str) -> None:
    assert ToolRiskClassifier().classify(tool) is ToolRiskLevel.HIGH


@pytest.mark.parametrize("tool", _standaardtools())
def test_elke_standaardtool_heeft_een_uitdrukkelijke_regel(tool: str) -> None:
    classifier = ToolRiskClassifier()

    assert tool in classifier._risk_levels, (  # noqa: SLF001 -- de bron zelf, geen afgeleide
        f"{tool} staat niet in tool_risk_levels.yml en valt dus stil op de standaard"
    )
