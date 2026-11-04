"""Alleen de erkende fabrieken mogen een JWT ondertekenen (OP-182).

Waarom deze toets bestaat. De Gate-2-reviewer van het dagplan gaf als sterkste
tegenargument: "de bron" is een fictie -- er zijn negen plekken in `src` die een JWT
produceren, na deze fix stempelen er twee, en over zes maanden lost iemand een 401 op door
zelf een token te ondertekenen zonder stempel. Dan is de markering iets wat de aanroeper
invult, en staat het gat weer open met een controle ervoor die zegt dat het dicht is.

Zonder deze toets is de stempel een CONVENTIE, en conventies overleven geen deadline.

De toets is deny-by-default: hij scant alles en eist dat elke ondertekenplek in de
gedateerde uitzonderingslijst staat. Hij dekt de signeer-ingangen van BEIDE bibliotheken
die dit project gebruikt -- python-jose EN PyJWT -- want een verbod op een enkele spelling
mist de volgende bibliotheek die erbij komt.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

WORTEL = Path(__file__).resolve().parents[2]
BRON = WORTEL / "src"

# Elke signeer-ingang van beide bibliotheken, niet alleen `jwt.encode`.
ONDERTEKENT = re.compile(
    r"\b(?:jwt|jose_jwt|jws|jose\.jwt|jose\.jws)\.(?:encode|sign)\s*\(|\bapi_jws\.encode\s*\("
)

# De plekken die op 2026-09-11 zijn gemeten en bewust blijven staan, met reden.
# Deze lijst GROEIT NIET zonder een expliciete wijziging: de lengte is hieronder
# vastgepind, zodat een zesde plek niet stil kan worden toegevoegd.
TOEGESTAAN: dict[str, str] = {
    "src/core/auth/jwt_handler.py": (
        "De fabriek. Stempelt at+jwt en refresh+jwt in de JOSE-header."
    ),
    "src/core/security/security_manager.py": (
        "Tweede fabriek met EEN levende aanroeper (POST /api/v1/security/auth/login, "
        "deprecated maar geregistreerd) op DEZELFDE sleutel. Stempelt sinds OP-182 mee."
    ),
    "src/core/auth/token_service.py": (
        "RS256 met kid, GEEN levende aanroeper gemeten op 2026-09-11. Eigen sleutelpaar, "
        "dus niet te verwarren met de HS256-tokens van de fabriek."
    ),
    "src/core/security/crypto_utils.py": (
        "Geen levende aanroeper gemeten op 2026-09-11."
    ),
    "src/core/security/jwt_handler_deprecated.py": (
        "Afgeschreven module, geen levende aanroeper voor de tokenfunctie gemeten op "
        "2026-09-11."
    ),
}


def _te_scannen_bestanden() -> list[Path]:
    """Alleen bestanden die git BIJHOUDT.

    Waarom niet gewoon de schijf aflopen: dan telt deze toets ook ongetrackte en
    genegeerde bestanden mee. Dat is precies misgegaan bij het samenvoegen met develop --
    `src/verify_tool_schema.py` staat in .gitignore (regel 353, `verify_*.py`) en is dus
    geen onderdeel van de codebase, maar hij ondertekende wel een JWT en maakte deze
    toets rood. Op een schone CI-machine bestaat zo'n bestand niet, dus dan zou de toets
    daar groen zijn en lokaal rood -- de vervelendste soort toets die er is.
    """
    try:
        uitvoer = subprocess.run(
            ["git", "ls-files", "--", "src/**/*.py", "src/*.py"],
            cwd=WORTEL,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        # Geen git beschikbaar: val terug op de schijf en accepteer de ruis, want een
        # toets die stil overslaat is erger dan een toets met een vals positief.
        return sorted(BRON.rglob("*.py"))
    paden = [WORTEL / regel.strip() for regel in uitvoer.splitlines() if regel.strip()]
    return [p for p in paden if p.suffix == ".py" and p.is_file()]


def _ondertekenplekken() -> set[str]:
    gevonden: set[str] = set()
    for bestand in _te_scannen_bestanden():
        try:
            inhoud = bestand.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for regel in inhoud.splitlines():
            gestript = regel.strip()
            if gestript.startswith("#"):
                continue
            if ONDERTEKENT.search(regel):
                gevonden.add(bestand.relative_to(WORTEL).as_posix())
                break
    return gevonden


def test_niemand_ondertekent_een_jwt_buiten_de_erkende_fabrieken() -> None:
    """De dragende richting: een NIEUWE ondertekenplek maakt deze toets rood."""
    onbekend = sorted(_ondertekenplekken() - set(TOEGESTAAN))
    assert not onbekend, (
        "Nieuwe plek(ken) die een JWT ondertekenen buiten de erkende fabrieken: "
        + ", ".join(onbekend)
        + ". Een token zonder soort-stempel in de JOSE-header wordt door "
        "jwt_handler.verify_token geweigerd. Onderteken via "
        "jwt_handler.create_access_token of create_refresh_token, of voeg deze plek "
        "met een reden en een datum toe aan TOEGESTAAN in deze toets."
    )


def test_de_uitzonderingslijst_is_niet_verouderd() -> None:
    """De andere richting: verdwijnt een uitzondering, dan hoort hij uit de lijst.

    Zonder deze toets groeit de lijst en krimpt hij nooit, en wordt hij binnen een jaar
    een verzameling namen die niemand meer durft weg te halen.
    """
    verdwenen = sorted(set(TOEGESTAAN) - _ondertekenplekken())
    assert not verdwenen, (
        "Deze plekken staan in TOEGESTAAN maar ondertekenen niets meer: "
        + ", ".join(verdwenen)
        + ". Haal ze uit de lijst."
    )


def test_de_lengte_van_de_uitzonderingslijst_staat_vast() -> None:
    """Vijf gemeten plekken op 2026-09-11. Een zesde vergt een bewuste wijziging van dit
    getal, en dus een reviewer die ernaar kijkt.

    Bewust GEEN toets die op een datum afgaat: een tijdbom die de bouw laat springen op
    een dag dat niemand klaarstaat is een nieuw defect, geen handhaving. Het vastpinnen
    van de lengte doet hetzelfde werk zonder die bijwerking.
    """
    assert len(TOEGESTAAN) == 5


def test_elke_uitzondering_heeft_een_reden() -> None:
    """Een uitzondering zonder reden is over een half jaar niet te beoordelen."""
    for pad, reden in TOEGESTAAN.items():
        assert len(reden) > 30, "Uitzondering zonder bruikbare reden: " + pad
