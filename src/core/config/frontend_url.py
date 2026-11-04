"""De basis-URL van de frontend voor links in mails (workflowscherm nazorg, punt 3).

Een uitnodiging of een wachtwoordherstel bevat een link naar de frontend. Viel `FRONTEND_URL` weg, dan ging er stil een link naar
`http://localhost:3000` de deur uit (gemeten door de acceptant): de medewerker kan er niets mee. Nu geldt: in een zachte omgeving
(`ZACHTE_OMGEVINGEN`: development, dev, local, test, testing) blijft localhost de bedoelde terugval; ELDERS, ook bij een onbekende of
verkeerd gespelde omgevingsnaam, is een ontbrekende of onbruikbare `FRONTEND_URL` een fout. Het opstarten roept dit aan en weigert
dan te starten.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

STANDAARD_LOKAAL = "http://localhost:3000"


class FrontendUrlOntbreekt(RuntimeError):
    """`FRONTEND_URL` ontbreekt of is onbruikbaar in een omgeving waar een link naar localhost niets waard is."""


def frontend_url(omgeving: str | None = None) -> str:
    """De basis-URL zonder slash aan het eind; of een fout als ze buiten een zachte omgeving ontbreekt.

    `omgeving` valt terug op `ENVIRONMENT`, en zonder die op `production` (zelfde standaard als `src/main.py`).
    """
    from src.core.database.applicatierol_controle import ZACHTE_OMGEVINGEN

    naam = (omgeving or os.getenv("ENVIRONMENT") or "production").strip().lower()
    waarde = os.getenv("FRONTEND_URL", "").strip().rstrip("/")

    if not waarde:
        if naam in ZACHTE_OMGEVINGEN:
            return STANDAARD_LOKAAL
        raise FrontendUrlOntbreekt(
            f"FRONTEND_URL ontbreekt in omgeving '{naam}': een uitnodiging of wachtwoordherstel zou een link naar localhost "
            "bevatten. Zet FRONTEND_URL op het adres van de frontend (bijvoorbeeld https://app.example.org)."
        )
    delen = urlsplit(waarde)
    if delen.scheme.lower() not in ("http", "https") or not delen.hostname:
        raise FrontendUrlOntbreekt(
            f"FRONTEND_URL moet met http:// of https:// beginnen en een adres bevatten (omgeving '{naam}'); een link zonder dat "
            "werkt niet in een mail."
        )
    if delen.username or delen.password or delen.query or delen.fragment:
        raise FrontendUrlOntbreekt(
            f"FRONTEND_URL mag geen gebruikersnaam, wachtwoord, query of fragment bevatten (omgeving '{naam}')."
        )
    if naam not in ZACHTE_OMGEVINGEN and (
        delen.scheme.lower() != "https" or delen.hostname in ("localhost", "127.0.0.1", "::1")
    ):
        raise FrontendUrlOntbreekt(
            f"FRONTEND_URL moet in omgeving '{naam}' een https-adres zijn dat niet naar localhost wijst: een herstellink gaat "
            "met een token in de URL de deur uit."
        )
    return waarde
