"""Mutatiebewijs voor de OP-154-borging.

Dekt twee dingen:
  1. `tests/architecture/test_bypass_lezen_en_schrijven_blijven_bij_elkaar.py` -- de guard.
  2. `tests/unit/core/database/test_bypass_session_faalt_luid.py` -- de fail-secure-belofte
     van `src/core/database/bypass_session.py`.

EEN REGEL PER ELEMENT van de bewaakte verzameling (ADR-036 OP-124-nazorg), plus beide
tegenrichtingen. Draai vanuit de worktree:

    python scripts/bewijs_op154_guard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.mutation_harness import (  # noqa: E402
    Mutation,
    assert_sole_writer,
    replace_anchor,
    verify_green,
    verify_red,
)

WORKTREE = Path(__file__).resolve().parents[1]
GUARD = "tests/architecture/test_bypass_lezen_en_schrijven_blijven_bij_elkaar.py"
NIEUW = f"{GUARD}::test_geen_nieuwe_gevallen"
STALE = f"{GUARD}::test_lijst_is_niet_verouderd"

PYTEST = [sys.executable, "-m", "pytest", "-q", "--timeout=120", "-p", "no:randomly"]

# De bewaakte elementen: (bestand, functienaam) zoals ze in KNOWN staan.
#
# Waren er acht op 2026-09-15 bij aanvang van stap 2. De vijf op het authenticatiepad zijn
# die dag omgezet.
#
# LET OP -- hier stond een onjuiste claim: dat `test_lijst_is_niet_verouderd` bij elke
# omzetting rood werd en dat DAARMEE de omzetting vijf keer bewezen was. De Gate 2-review
# van 2026-09-15 heeft dat weerlegd: die roodheid betekende "de guard herkent deze functie
# niet meer", niet "het patroon is opgelost". Het echte bewijs staat in
# `OMGEZETTE_PLEKKEN` hieronder, dat de productiecode muteert in plaats van deze lijst.
#
# Deze drie blijven: het zijn geen verzoekpaden maar een seeder en twee opruimtaken die
# over ALLE tenants werken. Die kunnen geen tenant "aannemen" en horen bij OP-153 (fase C).
ELEMENTEN = [
    ("src/core/company/seed_templates.py", "seed_platform_templates"),
    ("src/workers/actors.py", "_run_stale_task_cleanup"),
    ("src/workers/actors.py", "cleanup_expired_hitl_tickets"),
]


def bewijs_per_element() -> None:
    """Elk element apart uit KNOWN halen moet de guard ROOD maken."""
    for bestand, functie in ELEMENTEN:
        with Mutation(GUARD) as m:
            tekst = m.text
            # Knip precies de dict-regel van dit element weg door de sleutel te hernoemen
            # naar iets dat niet bestaat; de gevonden plek staat dan niet meer in KNOWN.
            m.write(
                replace_anchor(tekst, f'"{functie}",\n    ): ', f'"{functie}__GEMUTEERD",\n    ): ')
            )
            verify_red(PYTEST + [NIEUW], cwd=WORKTREE)
        print(f"  ROOD zoals verwacht bij het weghalen van {bestand}::{functie}()")


#: De VIJF omgezette auth-plekken, met per plek een mutatie die het OORSPRONKELIJKE
#: OP-154-geval terugzet: lezen binnen het blok, schrijven erbuiten.
#:
#: Deze lijst bestaat omdat het eerste bewijs ontoereikend was. Dat mat alleen het weghalen
#: van een regel uit `KNOWN_...`, en dat toont dat de guard een BEKENDE plek vindt -- niet
#: dat hij het PATROON herkent. Juist dat was stuk: na de omzetting naar
#: `pre_auth_lookup`/`adopt_tenant` zag de guard deze vijf functies helemaal niet meer, en
#: het terugzetten van de echte fout liet alle drie de architecture-guards GROEN.
#: Gevonden door de Gate 2-review van 2026-09-15.
OMGEZETTE_PLEKKEN = [
    (
        "src/core/api/auth/router_password.py",
        "reset_password",
        '        logger.info("password_reset_completed',
        '        user.hashed_password = "x"\n        await db.commit()\n'
        '        logger.info("password_reset_completed',
    ),
    (
        "src/core/api/auth/router_password.py",
        "change_password",
        '    logger.info("password_change_success',
        '    await db.commit()\n    logger.info("password_change_success',
    ),
    (
        "src/core/api/auth/router_login.py",
        "login",
        "        if not gevonden:",
        "        await db.commit()\n        if not gevonden:",
    ),
    (
        "src/core/api/auth/router_login.py",
        "get_or_create_lockout_record",
        # Uniek anker: `    return lockout` alleen komt tweemaal voor in dit bestand, en dan
        # muteert het harnas terecht NIETS -- een mutatie die niets muteert is niet te
        # onderscheiden van een guard die werkt.
        "        await db.commit()\n\n    return lockout",
        "        await db.commit()\n\n    db.add(lockout)\n    return lockout",
    ),
    (
        "src/core/auth/auth_service.py",
        "authenticate_user",
        "            # Dekt het HELE pad",
        "            await db.commit()\n            # Dekt het HELE pad",
    ),
]


def bewijs_omgezette_plekken() -> None:
    """Het oorspronkelijke OP-154-geval terugzetten MOET de guard rood maken.

    Dit is het bewijs dat de guard het patroon herkent en niet alleen een naam.
    """
    for bestand, functie, oud, nieuw in OMGEZETTE_PLEKKEN:
        with Mutation(bestand) as m:
            m.write(replace_anchor(m.text, oud, nieuw))
            verify_red(PYTEST + [GUARD], cwd=WORKTREE)
        print(f"  ROOD zoals verwacht bij het terugzetten van het OP-154-geval in {functie}()")


def bewijs_nieuw_geval() -> None:
    """Een NIEUW geval in PRODUCTIECODE moet worden betrapt."""
    doel = "src/core/api/auth/router_registration.py"
    with Mutation(doel) as m:
        tekst = m.text
        # Zet een commit NA het bypass-blok in register().
        m.write(
            replace_anchor(
                tekst,
                "    with TenantFilterBypass():",
                "    with TenantFilterBypass():\n        pass\n    await db.commit()\n    with TenantFilterBypass():",
            )
        )
        verify_red(PYTEST + [NIEUW], cwd=WORKTREE)
    print(f"  ROOD zoals verwacht bij een NIEUW geval in {doel}")


def bewijs_opgelost_geval() -> None:
    """Een OPGELOST geval moet de staleness-test ROOD maken."""
    doel = "src/core/company/seed_templates.py"
    with Mutation(doel) as m:
        tekst = m.text
        # Haal de bypass weg: de functie heeft dan geen bypass-blok meer en valt
        # dus uit de gevonden verzameling -- precies wat 'opgelost' betekent voor
        # deze guard.
        m.write(replace_anchor(tekst, "with TenantFilterBypass():", "if True:  # GEMUTEERD"))
        verify_red(PYTEST + [STALE], cwd=WORKTREE)
    print(f"  ROOD zoals verwacht bij een OPGELOST geval in {doel}")


MODULE = "src/core/database/bypass_session.py"
FAALTEST = "tests/unit/core/database/test_bypass_session_faalt_luid.py"


def bewijs_fail_secure() -> None:
    """De fail-secure-belofte van `bypass_session.py` is geen proza.

    Drie mutaties die elk een stille storing zouden introduceren; alle drie moeten de
    unittests ROOD maken.
    """
    mutaties = [
        (
            "een stille terugval op de gewone sessie",
            """    if not bypass_is_configured():
        raise BypassNietBeschikbaar(""",
            """    if not bypass_is_configured():
        from src.core.database.database import db_manager

        async with db_manager.get_session() as terugval:
            yield terugval
        return
    if False:
        raise BypassNietBeschikbaar(""",
        ),
        ("de BYPASSRLS-eis uitgezet", "    if not bypassrls:", "    if False:"),
        ("een superuser toegelaten", "    if is_superuser:", "    if False:"),
        # OP-154 stap 2: de twee helpers.
        (
            "pre_auth_lookup opent de tenantfilter-bypass NIET meer",
            "    with TenantFilterBypass():\n        if bypass_is_configured():",
            "    if True:\n        if bypass_is_configured():",
        ),
        (
            "adopt_tenant zet de vorige tenant NIET terug",
            "        if vorige is None:\n            clear_tenant_context()\n        else:\n            set_tenant_id(vorige)",
            "        pass",
        ),
        (
            "adopt_tenant zet de tenant helemaal niet",
            "    set_tenant_id(tenant_id)\n    try:",
            "    try:",
        ),
        # Deze staat er omdat het NIET vanzelf sprak: `clear_tenant_context()` in plaats van
        # de vorige waarde terugzetten lijkt onschuldig, maar wist op een geauthenticeerd
        # pad (`change_password`) de tenant die de middleware al had gezet -- de rest van
        # dat verzoek draait dan zonder context.
        (
            "adopt_tenant herstelt naar None i.p.v. de vorige waarde",
            "        if vorige is None:\n            clear_tenant_context()\n        else:\n            set_tenant_id(vorige)",
            "        clear_tenant_context()",
        ),
    ]
    for omschrijving, oud, nieuw in mutaties:
        with Mutation(MODULE) as m:
            m.write(replace_anchor(m.text, oud, nieuw))
            verify_red(PYTEST + [FAALTEST], cwd=WORKTREE)
        print(f"  ROOD zoals verwacht bij: {omschrijving}")
    verify_green(PYTEST + [FAALTEST], cwd=WORKTREE)
    print("  GROEN op de ongewijzigde boom (fail-secure)")


def bewijs_tegenrichting() -> None:
    """Ongewijzigd moet alles GROEN zijn -- anders bewijst het bovenstaande niets."""
    verify_green(PYTEST + [GUARD], cwd=WORKTREE)
    print("  GROEN op de ongewijzigde boom (tegenrichting)")


if __name__ == "__main__":
    assert_sole_writer(WORKTREE, "bewijs_op154_guard")
    try:
        print("Mutatiebewijs OP-154 -- het PATROON, een mutatie per omgezette plek:")
        bewijs_omgezette_plekken()
        print("Mutatiebewijs OP-154-guard -- een regel per nog-open element:")
        bewijs_per_element()
        print("Tegenrichtingen:")
        bewijs_nieuw_geval()
        bewijs_opgelost_geval()
        bewijs_tegenrichting()
        print("Fail-secure van bypass_session.py:")
        bewijs_fail_secure()
        print("\nAlle mutaties betrapt, en de ongewijzigde boom is groen.")
    finally:
        # `assert_sole_writer` legt een lockbestand neer en `mutation_harness` kent geen
        # release. Zonder deze regel faalt de VOLGENDE run met "Een ander proces muteert
        # deze worktree" -- gemeten tijdens de Gate 2-review, die het slot met de hand moest
        # opruimen.
        (WORKTREE / ".mutation-lock").unlink(missing_ok=True)
