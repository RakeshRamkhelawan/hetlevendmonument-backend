"""De regels voor een zelf gekozen wachtwoord: EEN bron voor aanmaken, herstellen en wijzigen.

Tot 2026-10-16 had elke deur zijn eigen regel: aanmaken (`UserCreate`) vroeg lengte, hoofdletter,
kleine letter en cijfer; herstellen en wijzigen vroegen alleen lengte; het resetscherm in de frontend
vroeg 12 tekens en een speciaal teken. Wat je op de ene plek mocht kiezen, werd op de andere
geweigerd of juist zonder controle aanvaard.

Inloggen hoort hier NIET bij: een wachtwoord komt nooit in een query maar wordt alleen gehasht
vergeleken, dus daar geldt alleen een lengtegrens (`router_login.py`). Een patroonfilter op het
wachtwoord (zoals voor zoekvelden) liet een gekozen `#`, `'`, `--` of `=...;` op het inlogscherm
weigeren met "password contains invalid characters".

Wijzig je de regels, wijzig dan ook de uitleg in `frontend/src/lib/wachtwoordRegels.ts`.
"""

from __future__ import annotations

import re

MIN_LENGTE = 8
MAX_LENGTE = 128


def controleer_gekozen_wachtwoord(wachtwoord: str) -> str:
    """Geef het wachtwoord terug als het aan de regels voldoet, anders `ValueError`."""
    if len(wachtwoord) < MIN_LENGTE:
        raise ValueError(f"Password must be at least {MIN_LENGTE} characters long")
    if len(wachtwoord) > MAX_LENGTE:
        raise ValueError(f"Password must be at most {MAX_LENGTE} characters long")
    if not re.search(r"[A-Z]", wachtwoord):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", wachtwoord):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"[0-9]", wachtwoord):
        raise ValueError("Password must contain at least one digit")
    if not wachtwoord.isascii():
        raise ValueError("Password must contain only ASCII characters")
    return wachtwoord
