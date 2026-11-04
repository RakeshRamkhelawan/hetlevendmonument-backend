"""Een taakrij van een uitvoering als regel voor de medewerker, in het Nederlands (agentstap dag 2, Keten G).

De engine bewaart per stap een Engelse statuscode, het resultaat en de fout. Dit maakt daar de regel van die de
uitvoeringsmonitor toont: de Nederlandse naam van de agent, een Nederlandse status, de uitkomst en bij een weigering de
reden. Geen stacktrace en geen interne foutnaam.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

STATUS_NL: dict[str, str] = {
    "pending": "Wacht op uitvoering",
    "running": "Bezig",
    "succeeded": "Uitgevoerd",
    "failed": "Mislukt",
    "retrying": "Wordt opnieuw geprobeerd",
    "timeout": "Te lang gewacht",
    "skipped": "Overgeslagen",
}


class _Taak(Protocol):
    task_ref: str
    task_type: str
    status: object
    result_json: object
    error_json: object


def _tekst(waarde: object) -> str | None:
    return waarde.strip() if isinstance(waarde, str) and waarde.strip() else None


def _agentnaam(agent_id: object) -> str | None:
    from src.core.als.agents.workflow_stap import AGENT_BESCHRIJVING

    if isinstance(agent_id, str) and agent_id in AGENT_BESCHRIJVING:
        return AGENT_BESCHRIJVING[agent_id][0]
    return None


def _agent_van_de_knoop(knoop: Mapping[str, object]) -> object:
    data = knoop.get("data")
    return knoop.get("agent_id") or (data.get("agent_id") if isinstance(data, dict) else None)


def _naam(taak: _Taak, resultaat: dict[str, object], knoop: Mapping[str, object]) -> str:
    """De naam die de medewerker de stap gaf, met de agent erachter; de technische sleutel is het laatste redmiddel."""
    agent = _agentnaam(resultaat.get("agent_id")) or _agentnaam(_agent_van_de_knoop(knoop))
    data = knoop.get("data")
    label = _tekst(data.get("label")) if isinstance(data, dict) else None
    # `name` komt uit een knoop die de workflowbouwer als `tasks` stuurt; de builderstore bewaart `{id, title, data}`.
    gegeven = _tekst(knoop.get("name")) or _tekst(knoop.get("title")) or label
    if gegeven and agent:
        return f"{gegeven} ({agent})"
    return gegeven or agent or taak.task_ref


def _uitkomst(resultaat: dict[str, object]) -> str | None:
    uitvoer = resultaat.get("output")
    if not isinstance(uitvoer, dict):
        return None
    for sleutel in ("summary", "samenvatting", "message"):
        tekst = _tekst(uitvoer.get(sleutel))
        if tekst:
            return tekst
    return None


VASTE_REDEN = "de stap is mislukt; vraag uw beheerder om het na te kijken"


def _reden(taak: _Taak, code: str) -> str | None:
    """Alleen een reden die voor de klant is gemaakt.

    De engine bewaart bij elke uitzondering `str(e)`; die tekst kan een adres met wachtwoord, SQL of een interne host
    bevatten. De agentstap zet bewust Nederlandse redenen in `StapMislukt`; al het andere krijgt een vaste tekst en het
    detail staat in het log van de engine.
    """
    fout = taak.error_json
    if isinstance(fout, dict):
        voor_de_klant = taak.task_type == "agent" and fout.get("type") == "StapMislukt"
        tekst = _tekst(fout.get("message")) if voor_de_klant else None
        return tekst or VASTE_REDEN
    if code in ("failed", "timeout"):
        return VASTE_REDEN
    return None


def stap_overzicht(
    taak: _Taak, knopen: Mapping[str, Mapping[str, object]] | None = None
) -> dict[str, str | None]:
    resultaat = taak.result_json if isinstance(taak.result_json, dict) else {}
    code = str(getattr(taak.status, "value", taak.status))
    return {
        "stap": taak.task_ref,
        "naam": _naam(taak, resultaat, (knopen or {}).get(taak.task_ref, {})),
        "status": STATUS_NL.get(code, "Onbekend"),
        "uitkomst": _uitkomst(resultaat),
        "reden": _reden(taak, code),
    }
