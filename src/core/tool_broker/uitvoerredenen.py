"""Vaste Nederlandse zinnen voor een goedgekeurde actie die niet kon worden uitgevoerd (crediteuren nazorg, punt 1).

Een tool die na goedkeuren faalt geeft naast zijn eigen tekst een CODE (`reden_code`). De goedkeurroute geeft nooit de tekst van de tool
terug (die kan payload-inhoud bevatten, zie `_voer_goedgekeurde_actie_uit`), maar zoekt de code hier op: wie goedkeurde ziet dan in
gewone taal waarom het niet lukte en wat er nu gebeurt. Een code die hier niet staat levert niets op; de gebruiker krijgt dan de algemene
tekst van het scherm.

Elke zin is vast: geen invulplaatsen, geen factuurnummers, geen namen en geen bedragen. Dat is met opzet; zo kan er nooit
leveranciersgegevens of vrije tekst in een melding terechtkomen.
"""

from __future__ import annotations

UITVOERREDENEN: dict[str, str] = {
    "iban_gewijzigd": (
        "Het rekeningnummer van een leverancier is gewijzigd na uw goedkeuring. Er is niets goedgekeurd; "
        "de facturen kunnen opnieuw worden voorgelegd: vraag de crediteurenagent om een nieuw voorstel."
    ),
    "factuur_veranderd": (
        "Een factuur is veranderd sinds het voorstel werd gemaakt. Er is niets goedgekeurd; "
        "de facturen kunnen opnieuw worden voorgelegd: vraag de crediteurenagent om een nieuw voorstel."
    ),
    "factuur_niet_meer_te_betalen": (
        "Een factuur stond niet meer klaar voor betaling, bijvoorbeeld omdat hij al is goedgekeurd of betaald. "
        "Er is niets goedgekeurd; vraag de crediteurenagent om een nieuw voorstel."
    ),
    "factuur_bestaat_niet_meer": (
        "Een factuur bestaat niet meer. Er is niets goedgekeurd; vraag de crediteurenagent om een nieuw voorstel."
    ),
    "voorstel_niet_uitvoerbaar": (
        "Het voorstel kon niet worden uitgevoerd omdat het niet meer klopt. Er is niets goedgekeurd; "
        "vraag de crediteurenagent om een nieuw voorstel."
    ),
    "factuur_of_leverancier_veranderd": (
        "De factuur of de leverancier is veranderd sinds dit voorstel werd gemaakt. Er is niets vastgelegd; "
        "de factuur kan opnieuw worden voorgelegd door hem opnieuw te laten verwerken."
    ),
    "iban_al_in_gebruik": (
        "Dit IBAN hoort al bij een andere leverancier van uw bedrijf. Er is niets vastgelegd; "
        "controleer of dit dezelfde leverancier is."
    ),
    "factuur_al_vastgelegd": (
        "Deze factuur is al vastgelegd of hoort bij een ander voorstel. Er is niets dubbel vastgelegd."
    ),
    "factuur_niet_meer_leesbaar": (
        "De factuur kan niet meer worden gelezen. Leg hem met de hand vast op de pagina Crediteuren."
    ),
    "gegevens_onzeker": (
        "Er ontbreken gegevens of ze zijn onzeker, of de valuta is niet euro. Er is niets vastgelegd; "
        "pas de factuur aan of leg hem met de hand vast."
    ),
}


def zin_voor(code: object) -> str | None:
    """De vaste zin bij een code, of `None` als de code niet bekend is (ook bij een niet-tekst)."""
    return UITVOERREDENEN.get(code) if isinstance(code, str) else None
