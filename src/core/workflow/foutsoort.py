"""Welke fouten een nieuwe poging verdienen (workflowscherm nazorg, punt 1).

Een nieuwe poging van een workflowstap of -uitvoering kan een taalmodelaanroep kosten. Daarom geldt: ALLEEN een fout die bekend
is als tijdelijk krijgt een nieuwe poging (netwerk, time-out, een gemelde "te veel verzoeken" of een tijdelijk onbereikbare
dienst, een hervatbare noodstop), en dan met een maximum. Alles wat niet bekend is als tijdelijk (validatie, rechten, een weigering, een
mislukte stap, een onbekende fout) krijgt er geen: onbekend is bij geldkosten "niet opnieuw".

De fout wordt samen met zijn oorzaken (`__cause__`, `__context__`) beoordeeld, want een tijdelijke fout is vaak verpakt in een
andere. Een fout die zelf een eigenschap `tijdelijk` heeft (een mislukte stap) beslist daar zelf over.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx

#: HTTP-statussen die om een nieuwe poging vragen: time-out, te veel verzoeken en een tijdelijk onbereikbare dienst.
TIJDELIJKE_STATUSSEN = frozenset({408, 429, 502, 503, 504})

#: Getypte fouten van de taalmodelaanbieders voor "te veel verzoeken". Bewust op TYPE, niet op de tekst van de fout: een
#: stapnaam of opdracht van een medewerker die "te veel verzoeken" bevat en in een foutmelding terugkomt, mag een fout niet
#: tijdelijk maken (dat zou nieuwe pogingen en dus taalmodelgeld kosten; Gate 2 security, workflowscherm nazorg).
_TE_DRUK_TYPEN = frozenset({"LLMRateLimitError"})

_MAX_DIEPTE = 8


def _is_tijdelijk_type(fout: BaseException) -> bool:
    if isinstance(fout, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    if isinstance(fout, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(fout, httpx.HTTPStatusError):
        return fout.response.status_code in TIJDELIJKE_STATUSSEN
    naam = type(fout).__name__
    if naam == "KlantStilgezet":
        # Een noodstop per klant is hervatbaar na het opheffen (zie `execute_workflow`).
        return True
    return naam in _TE_DRUK_TYPEN


def is_tijdelijke_fout(fout: BaseException) -> bool:
    """Is dit een fout waarvoor een nieuwe poging zin heeft (en geld waard is)?"""
    gezien: set[int] = set()
    huidig: BaseException | None = fout
    diepte = 0
    while huidig is not None and id(huidig) not in gezien and diepte < _MAX_DIEPTE:
        gezien.add(id(huidig))
        if getattr(huidig, "uitvoering_beeindigd", False):
            return False
        eigen = getattr(huidig, "tijdelijk", None)
        if isinstance(eigen, bool):
            return eigen
        if _is_tijdelijk_type(huidig):
            return True
        # Alleen `__cause__` (`raise ... from ...`): `__context__` is ook de fout die per ongeluk tijdens het afhandelen ontstond.
        huidig = huidig.__cause__
        diepte += 1
    return False


def moet_opnieuw(max_pogingen: int) -> Callable[[int, BaseException], bool]:
    """De regel voor `retry_when` van een dramatiq-actor.

    Zodra `retry_when` is gezet, negeert dramatiq `max_retries`: het maximum zit dus in deze regel. `pogingen` is het aantal
    nieuwe pogingen dat al is gedaan.
    """

    def regel(pogingen: int, fout: BaseException) -> bool:
        return pogingen < max_pogingen and is_tijdelijke_fout(fout)

    return regel
