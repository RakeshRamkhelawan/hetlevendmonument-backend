"""Central environment file loader.

Called ONCE from src/main.py before any other imports.
All other modules must NOT call load_dotenv() directly.
"""

import os
from pathlib import Path


def setup_environment(root: Path | None = None) -> None:
    """Load env files in strict precedence order.

    Order (lowest -> highest priority):
      1. .env              (base defaults)
      2. .env.{ENVIRONMENT} (environment-specific, e.g. .env.development)
      3. .env.local         (local secrets, git-ignored)

    Pre-existing os.environ values are always respected -- voor ELKE sleutel, niet alleen
    voor DATABASE_URL. Wat de operator heeft geexporteerd (Docker compose, CI, een shell)
    wint van elk bestand; `.env.local` wint alleen van de andere BESTANDEN.

    Tot 2026-09-15 klopte die belofte niet: `.env.local` werd met `override=True` geladen en
    overschreef daarmee ook geexporteerde waarden (ADR-036 OP-243).
    """
    from dotenv import load_dotenv

    if root is None:
        root = Path(__file__).resolve().parent.parent.parent  # repo root

    # Wat de operator zelf heeft gezet, wint van ELK bestand (ADR-036 OP-243).
    #
    # Hier stond `load_dotenv(local_file, override=True)` plus een guard die de hele functie
    # oversloeg zodra DATABASE_URL gezet was. Twee problemen:
    #   1. `override=True` in python-dotenv maakt GEEN onderscheid tussen "al gezet door een
    #      eerder dotenv-bestand" en "door de operator geexporteerd". De bedoeling -- een
    #      lokaal bestand wint van de andere BESTANDEN -- klopte; de uitvoering haalde ook de
    #      echte omgeving onderuit. `.env.local` is gitignored, dus dat is een onzichtbaar
    #      bestand dat een expliciete keuze overstemt.
    #   2. De guard koppelde de HELE loader aan EEN sleutel: was DATABASE_URL gezet, dan werd
    #      er niets geladen -- ook de sleutels niet die wel uit een bestand hadden moeten
    #      komen.
    # Beide zijn opgelost door de vooraf gezette omgeving na afloop terug te zetten. Daarmee
    # wint `.env.local` nog steeds van `.env` en `.env.<omgeving>`, en wint de omgeving van
    # alles. De guard is daardoor overbodig geworden en verwijderd.
    vooraf_gezet = dict(os.environ)

    load_dotenv(root / ".env", override=False)

    env = os.getenv("ENVIRONMENT", "development")
    env_file = root / f".env.{env}"
    if env_file.exists():
        load_dotenv(env_file, override=False)

    local_file = root / ".env.local"
    if local_file.exists():
        load_dotenv(local_file, override=True)

    # Herstel: alles wat er voor het laden al stond, staat er weer precies zo.
    os.environ.update(vooraf_gezet)
