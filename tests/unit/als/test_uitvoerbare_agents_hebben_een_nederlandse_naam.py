"""Elke agent die een agentstap kan uitvoeren heeft een Nederlandse naam en omschrijving (agentstap dag 2).

De workflowbouwer toont die tekst aan een medewerker; zonder deze toets verschijnt een nieuw bedrade agent met zijn
Engelse catalogusnaam of zonder uitleg. De tekst staat in `AGENT_BESCHRIJVING` (`src/core/als/agents/workflow_stap.py`).

Mutatiebewijs (2026-10-25): een sleutel uit `AGENT_BESCHRIJVING` halen -> de eerste toets ROOD; een omschrijving leegmaken ->
de tweede ROOD; de tegenrichting (alle vier ingevuld) is de huidige stand en groen.
"""

from __future__ import annotations

from src.core.als.agents.workflow_stap import AGENT_BESCHRIJVING
from src.core.als.enterprise.packs import UITVOERBARE_AGENT_SLEUTELS


def test_elke_uitvoerbare_agent_heeft_een_nederlandse_beschrijving() -> None:
    zonder = sorted(UITVOERBARE_AGENT_SLEUTELS - set(AGENT_BESCHRIJVING))

    assert zonder == [], (
        f"deze uitvoerbare agents hebben geen Nederlandse naam en omschrijving: {zonder}"
    )


def test_naam_en_omschrijving_zijn_niet_leeg() -> None:
    leeg = sorted(
        sleutel
        for sleutel, (naam, omschrijving) in AGENT_BESCHRIJVING.items()
        if not naam.strip() or not omschrijving.strip()
    )

    assert leeg == [], f"lege naam of omschrijving bij: {leeg}"


def test_er_staat_geen_agent_in_die_niet_uitvoerbaar_is() -> None:
    """Een beschrijving voor een agent die niet (meer) bedraad is, hoort er niet te staan."""
    overbodig = sorted(set(AGENT_BESCHRIJVING) - UITVOERBARE_AGENT_SLEUTELS)

    assert overbodig == [], f"beschrijving voor een niet-uitvoerbare agent: {overbodig}"
