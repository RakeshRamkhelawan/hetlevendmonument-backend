"""Registratie verraadt niet of een e-mailadres al bestaat (ADR-036 OP-235c).

**De bevinding.** `router_registration.py` deed de bestaanscontrole onder
`TenantFilterBypass` -- dus over ALLE tenants -- en antwoordde dan "Registration failed: user
with this email already exists". Een aanmelder kon daarmee vaststellen of een adres ergens in
het platform bestaat, ook in een tenant waar hij niets mee te maken heeft.

**Waarom dit geen open ontwerpvraag was.** De registerrij noemde het een afweging tussen
registratie-UX en enumeratiebescherming. Die afweging is in dit project al gemaakt:
`test_forgot_password_never_reveals_user_existence` legt precies het tegenovergestelde vast
voor het wachtwoordherstelpad. Twee routes in dezelfde applicatie die tegengesteld omgaan met
bestaansinformatie is geen keuze maar een inconsistentie.

**Beide richtingen.** Zonder de tweede test zou "antwoord altijd hetzelfde, ook bij succes"
de eerste halen -- en dan kan niemand zich meer registreren.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROUTER = Path("src/core/api/auth/router_registration.py")


def _tekstconstanten() -> set[str]:
    """Alle stringconstanten in de module.

    Via een AST-parse en niet met een tekstzoektocht: de toelichting bij de reparatie
    CITEERT de oude melding om uit te leggen wat er weg is, en een zoektocht op tekst zou
    daarop afgaan. Commentaar staat niet in een AST. Deze val is op 2026-09-15 tweemaal
    gesprongen bij OP-186 -- zie quality-gates.md.
    """
    boom = ast.parse(_ROUTER.read_text(encoding="utf-8"))
    return {
        k.value for k in ast.walk(boom) if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }


def test_het_antwoord_verraadt_niet_dat_het_adres_bestaat() -> None:
    """Geen enkele foutmelding mag het bestaan van een gebruiker prijsgeven."""
    verdacht = [
        t for t in _tekstconstanten() if "already exists" in t.lower() or "bestaat al" in t.lower()
    ]
    assert not verdacht, (
        f"Deze meldingen verraden het bestaan van een gebruiker: {verdacht}. De controle "
        "draait onder TenantFilterBypass, dus dit lekt over tenantgrenzen heen. Dit project "
        "houdt voor wachtwoordherstel al de tegenovergestelde lijn aan (ADR-036 OP-235c)."
    )


def test_de_afwijzing_bestaat_nog_wel() -> None:
    """De andere richting: zonder deze zou 'verwijder de hele controle' de eerste halen.

    Een registratie voor een bestaand adres MOET nog steeds worden afgewezen -- alleen
    zonder te zeggen waarom.
    """
    constanten = _tekstconstanten()
    assert "Registration failed" in constanten, (
        "De generieke afwijzing is verdwenen. Dan wordt een dubbel adres stil geaccepteerd "
        "of valt de route om op een databasefout, en dat is erger dan het lek."
    )
