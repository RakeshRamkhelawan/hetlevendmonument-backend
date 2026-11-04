"""Elke `UserResponse` die de frontend bereikt, beantwoordt de beheerdersvraag (OP-193).

**Waarom deze guard bestaat, en hij komt uit een gemiste plek en niet uit een idee.**
OP-193 gaf `api/auth/schemas.UserResponse` een veld `is_admin`, omdat de frontend
beheerderschap niet uit de tokenscopes kan afleiden (ADR-036 OP-186 haalde de loper op
rolnaam er bewust uit). `get_me` vulde het. `login()` NIET -- en dat is uitgerekend het pad
dat de frontend gebruikt om zijn store te vullen, zonder een extra `/me`-aanroep; de comment
boven die constructie zegt dat zelf. Gevolg zou zijn geweest: een beheerder die via het
formulier inlogt krijgt de Pydantic-default `False` en wordt tot de volgende volledige
paginaherlading op alle zeven beheerdersroutes naar `/forbidden` gestuurd -- precies de
storing die OP-193 oplost, alleen verplaatst naar het inlogpad.

Gevonden door de Gate 2-security-review van 2026-09-19, niet door een test. Deze guard is
die ontbrekende test.

**Waarom AST en geen tekstzoektocht.** `is_admin` komt in dat bestand ook voor als import,
als functienaam en in commentaar. Een `grep` zou dus groen blijven bij een constructie die
het veld NIET meegeeft. Deze guard leest de daadwerkelijke aanroep en kijkt naar de
sleutelwoord-argumenten.

**Mutatiebewijs (2026-09-19), beide richtingen, terugweg via een kopie:**

    `is_admin=...` uit de constructie in `login()` gehaald   -> 1 failed, met regelnummer 403
    `is_admin=...` uit de constructie in `get_me` gehaald    -> 1 failed, met regelnummer 466
    beide weggehaald                                        -> 1 failed, beide regels genoemd
    ongemuteerd                                             -> 2 passed
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER = REPO_ROOT / "src" / "core" / "api" / "auth" / "router_login.py"

#: Het veld dat elke constructie moet meegeven.
VELD = "is_admin"


def _noemt_userresponse(knoop: ast.AST) -> bool:
    """Bevat deze deelboom een verwijzing naar `UserResponse`?

    Dekt zowel `UserResponse(...)` als `UserResponse.model_validate(...)`. Dat tweede is
    geen detail: `get_me` bouwt het antwoord met `model_validate` omdat een handmatige
    constructie STRENGER is dan FastAPI's eigen coercie en daarmee een pad brak (een
    bronobject hoeft de optionele velden niet te hebben). Een guard die alleen de
    constructorvorm kent, zou daarna stil groen zijn geworden op een bestand waar het
    antwoord ontbreekt.
    """
    for sub in ast.walk(knoop):
        if isinstance(sub, ast.Name) and sub.id == "UserResponse":
            return True
    return False


def _noemt_het_veld(knoop: ast.AST) -> bool:
    """Komt `is_admin` in deze deelboom voor als keyword-argument of als dict-sleutel?

    Beide vormen tellen: `UserResponse(..., is_admin=...)` en
    `...model_copy(update={"is_admin": ...})`.
    """
    for sub in ast.walk(knoop):
        if isinstance(sub, ast.keyword) and sub.arg == VELD:
            return True
        if isinstance(sub, ast.Constant) and sub.value == VELD:
            return True
    return False


def _userresponse_constructies() -> list[ast.stmt]:
    """Elke `return`/toekenning die een `UserResponse` voor de frontend oplevert."""
    boom = ast.parse(ROUTER.read_text(encoding="utf-8"))
    return [
        knoop
        for knoop in ast.walk(boom)
        if isinstance(knoop, (ast.Return, ast.Assign))
        and knoop.value is not None
        and isinstance(knoop.value, ast.Call)
        and _noemt_userresponse(knoop.value)
    ]


def test_elke_userresponse_geeft_het_beheerdersantwoord_mee() -> None:
    zonder = [
        statement.lineno
        for statement in _userresponse_constructies()
        if not _noemt_het_veld(statement)
    ]

    assert not zonder, (
        f"Deze `UserResponse(...)`-constructies in {ROUTER.name} geven `{VELD}` niet mee "
        f"(regel {zonder}). Het veld krijgt dan de Pydantic-default `False`, ook voor een "
        "echte beheerder, en de frontend stuurt hem naar /forbidden op alle zeven "
        "beheerdersroutes. Precies dat gebeurde op het inlogpad; zie ADR-036 OP-193.\n"
        "Let bij het repareren op WAT je doorgeeft: `is_admin()` telt alleen rolnamen die "
        "een string zijn, en op het ORM-object zijn `user.roles` OBJECTEN."
    )


def test_de_guard_meet_iets() -> None:
    """Een parse die niets vindt maakt de test hierboven trivially groen."""
    aantal = len(_userresponse_constructies())
    assert aantal >= 2, (
        f"Slechts {aantal} `UserResponse(...)`-constructies gevonden in {ROUTER.name}. Op "
        "2026-09-19 waren het er twee: het inlogpad (regel 403) en `get_me` (regel 466). "
        "Is het bestand gesplitst of heet de klasse anders, werk dan deze guard bij -- hij "
        "meet nu mogelijk niets."
    )
