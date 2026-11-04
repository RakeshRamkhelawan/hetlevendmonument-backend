"""Startcontrole op de databaserol van de applicatie (ADR-036 OP-151, brief 2026-10-21).

**Waarom.** Row Level Security wordt niet toegepast op de EIGENAAR van een tabel, niet op een superuser en niet op
een rol met BYPASSRLS. Verbindt de applicatie met zo'n rol, dan zijn alle ~180 policies decoratie: elke pagina
werkt, geen test wordt rood, en de scheiding tussen klanten rust stilletjes alleen nog op de applicatiecode. Een
vergeten `WHERE` lekt dan de gegevens van een andere klant. Er bestond geen enkele controle die dit opmerkte; de
toets in `bypass_session.py` betreft alleen de aparte pre-authenticatieverbinding.

**Wat er gebeurt.** Direct na het initialiseren van de database wordt de rol van de applicatieverbinding gemeten:
superuser? BYPASSRLS? eigenaar van een tabel met RLS? Is een van de drie waar:

- **elke omgeving behalve ontwikkeling/test:** de applicatie weigert te starten (`ApplicatieRolFout`), met de reden in gewone taal;
- **ontwikkeling, dev, local, test, testing:** een waarschuwing in het log;
- **`single_tenant`** (een klant, een installatie, ook offline): een CRITICAL-waarschuwing, ook in productie. Er is dan
  geen andere klant om te lekken en een installatie met de standaardrol `postgres` hoort te blijven starten.

SQLite (de unittests) kent geen rollen en wordt overgeslagen.

**Wat dit NIET doet.** Het wijzigt geen rol of recht, en het controleert niet of `FORCE ROW LEVEL SECURITY` aanstaat
(dat helpt alleen tegen de eigenaar, niet tegen een superuser; zie het reviewdocument). Het vertelt niet welke rol
een omgeving HOORT te gebruiken; dat staat in `docs/runbooks/applicatie-databaserol.md`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

#: Omgevingen waarin een verkeerde rol ALLEEN een waarschuwing is. Al het andere -- ook een onbekende of
#: verkeerd gespelde naam als `prod` of `live` -- is streng (fail-closed): een typefout hoort de start niet
#: stilletjes te versoepelen (Gate 2 ronde 1, F1).
ZACHTE_OMGEVINGEN = frozenset({"development", "dev", "local", "test", "testing"})


class ApplicatieRolFout(RuntimeError):
    """De applicatie verbindt met een databaserol waarop Row Level Security niet werkt."""


@dataclass(frozen=True)
class RolMeting:
    """Wat er over de rol van de verbinding bekend is."""

    rol: str
    rolsuper: bool
    heeft_bypassrls: bool
    #: Aantal tabellen in `public` met RLS aan waarvan deze rol de eigenaar is OF waarvan hij via
    #: lidmaatschap (INHERIT) de rechten van de eigenaar erft; ook dan past PostgreSQL RLS niet toe.
    eigen_rls_tabellen: int


_MEETVRAAG = text(
    """
    SELECT current_user,
           (SELECT rolsuper FROM pg_roles WHERE rolname = current_user),
           (SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user),
           (SELECT count(*) FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public'
               AND c.relkind IN ('r', 'p')
               AND c.relrowsecurity
               AND pg_has_role(current_user, c.relowner, 'USAGE'))
    """
)


async def meet_rol(conn: AsyncConnection) -> RolMeting:
    """Meet de rol van deze verbinding (alleen lezen)."""
    rij = (await conn.execute(_MEETVRAAG)).first()
    if rij is None:  # pragma: no cover - PostgreSQL geeft hier altijd een rij
        raise ApplicatieRolFout("De rolcontrole op de databaseverbinding gaf geen antwoord.")
    rol, rolsuper, heeft_bypassrls, eigen = rij
    return RolMeting(
        rol=str(rol),
        rolsuper=bool(rolsuper),
        heeft_bypassrls=bool(heeft_bypassrls),
        eigen_rls_tabellen=int(eigen or 0),
    )


def beoordeel_rol(meting: RolMeting) -> list[str]:
    """De problemen met deze rol, in gewone taal; leeg als de rol RLS niet omzeilt."""
    problemen: list[str] = []
    if meting.rolsuper:
        problemen.append("een superuser (PostgreSQL past RLS nooit toe op een superuser)")
    if meting.heeft_bypassrls:
        problemen.append("een rol met BYPASSRLS (die slaat RLS expliciet over)")
    if meting.eigen_rls_tabellen:
        problemen.append(
            f"de eigenaar (of lid van de eigenaarrol) van {meting.eigen_rls_tabellen} tabellen met RLS "
            "(PostgreSQL past RLS niet toe op de eigenaar, tenzij FORCE aanstaat)"
        )
    return problemen


async def controleer_applicatierol(
    conn: AsyncConnection, *, omgeving: str, single_tenant: bool
) -> None:
    """Weiger de start (productie/staging) of waarschuw (overig) als de rol RLS omzeilt."""
    if conn.dialect.name != "postgresql":
        return  # SQLite (unittests) kent geen rollen en geen RLS.

    meting = await meet_rol(conn)
    problemen = beoordeel_rol(meting)
    if not problemen:
        logger.info(
            "Databaserol van de applicatie: %s (geen superuser, geen BYPASSRLS, geen eigenaar): RLS werkt",
            meting.rol,
        )
        return

    uitleg = "; ".join(problemen)
    melding = (
        f"De applicatie verbindt met de databaserol '{meting.rol}': {uitleg}. Row Level Security beschermt dan "
        "NIET en de scheiding tussen klanten rust alleen op de applicatiecode. Gebruik de applicatierol "
        "'sanskritisetu_app' (docs/runbooks/applicatie-databaserol.md)."
    )
    if omgeving.strip().lower() not in ZACHTE_OMGEVINGEN:
        if not single_tenant:
            raise ApplicatieRolFout(melding)
        logger.critical(
            "RLS werkt niet voor deze verbinding en DEPLOYMENT_MODE=single_tenant houdt de start open "
            "(omgeving=%s). Op een gedeelde omgeving met meerdere klanten is dit een lek: %s",
            omgeving,
            melding,
        )
        return
    logger.warning("RLS werkt niet voor deze verbinding (omgeving=%s): %s", omgeving, melding)
