"""De begroeting van de workflowassistent spreekt de medewerker met 'u' aan (studio deel 2, punt 6).

De frontend gebruikt overwegend 'u' (gemeten 2026-10-28: 97 regels met 'u' tegen 38 met 'je'); de begroeting die de
backend in het assistentpaneel zet gebruikte 'je'. Het paneel kon daardoor in een en hetzelfde scherm van vorm wisselen.

Mutatiebewijs (2026-10-28): een van de drie begroetingen terug op 'je': de test van die tak rood. De andere kant op: de
begroeting blijft een volledige zin die de medewerker uitnodigt te vertellen wat er gebouwd moet worden (`..._nodigt_uit`).
"""

from __future__ import annotations

import re

import pytest

from src.core.agents.focus_builder_chat_agent import FocusBuilderChatAgent

JE_VORMEN = re.compile(r"\b(je|jij|jou|jouw|jezelf)\b", re.IGNORECASE)


def _begroeting(profiel: dict[str, object] | None) -> str:
    agent = object.__new__(FocusBuilderChatAgent)
    agent._twin_profile = profiel  # type: ignore[attr-defined]
    return agent._build_greeting()  # type: ignore[attr-defined]


GEVALLEN = {
    "zonder profiel": None,
    "met profiel zonder waarnemingen": {"observation_count": 0},
    "met profiel met waarnemingen": {"observation_count": 5},
}


@pytest.mark.unit
@pytest.mark.parametrize("naam", sorted(GEVALLEN))
def test_de_begroeting_gebruikt_geen_je_vorm(naam: str) -> None:
    assert JE_VORMEN.findall(_begroeting(GEVALLEN[naam])) == []


@pytest.mark.unit
@pytest.mark.parametrize("naam", sorted(GEVALLEN))
def test_de_begroeting_spreekt_met_u_aan(naam: str) -> None:
    assert re.search(r"\b(u|uw)\b", _begroeting(GEVALLEN[naam]), re.IGNORECASE)


@pytest.mark.unit
@pytest.mark.parametrize("naam", sorted(GEVALLEN))
def test_de_begroeting_nodigt_uit_om_te_vertellen_wat_er_gebouwd_moet_worden(naam: str) -> None:
    tekst = _begroeting(GEVALLEN[naam]).lower()

    assert tekst.count("vertel") == 1 and ("automatiseren" in tekst or "bouwen" in tekst)
