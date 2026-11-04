"""De actor `signaleer_hr_termijnen` roept de echte kern aan met de sessiefabriek van de worker.

De Dramatiq-ingang geeft zijn taak aan `draai_in_eigen_loop`, die een verse event loop en een
eigen engine opzet en de taak een sessiefabriek geeft. Deze test vervangt alleen die opzet (geen
database nodig) en toetst dat de taak de fabriek doorgeeft aan `signaleer_hr_termijnen_async`;
de kern zelf staat in `tests/integration/test_hr_pilot_dag4_dagelijkse_melding.py`.

Wat NIET gemeten is: een echte workerrun op de gedeelde pool (twee runs na elkaar); dat is de
acceptatie met een draaiende worker.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from src.core.tasks import hr_termijn_tasks


def test_de_actor_geeft_de_sessiefabriek_door_aan_de_kern(monkeypatch: pytest.MonkeyPatch) -> None:
    ontvangen: dict[str, Any] = {}

    async def _kern(sessie_fabriek: Any = None, nu: Any = None) -> int:
        ontvangen["fabriek"] = sessie_fabriek
        return 0

    def _draai(taak: Callable[[Any], Any]) -> None:
        asyncio.run(taak("de-fabriek"))

    monkeypatch.setattr(hr_termijn_tasks, "signaleer_hr_termijnen_async", _kern)
    monkeypatch.setattr(hr_termijn_tasks, "draai_in_eigen_loop", _draai)

    hr_termijn_tasks.signaleer_hr_termijnen.fn()

    assert ontvangen == {"fabriek": "de-fabriek"}


def test_de_actor_heet_zoals_de_scheduler_hem_aanroept() -> None:
    assert hr_termijn_tasks.signaleer_hr_termijnen.actor_name == "signaleer_hr_termijnen"


def test_de_actor_probeert_niet_opnieuw() -> None:
    # De sleutel per termijn en dag maakt een herhaling onschadelijk, maar de volgende dagrun pakt
    # wat blijft liggen: een nieuwe poging binnen dezelfde run is niet nodig.
    assert hr_termijn_tasks.signaleer_hr_termijnen.options["max_retries"] == 0
