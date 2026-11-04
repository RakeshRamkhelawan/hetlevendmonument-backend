"""De accountstatus van een token-houder, zonder cache (uitgeschakeld is uitgeschakeld).

Een token blijft cryptografisch geldig tot het verliep en zegt niets over de toestand van het
account. Deze module is de ENE plek die voor een ingang zonder `UserResponse` (de tenant
middleware, de WebSocket-ingangen) vaststelt of het account nog aan staat.

**Bewust GEEN cache.** Een cache zonder invalidatie heeft eerder een uur lang ingetrokken rechten
laten werken (OP-254). Een uitgezet account moet bij het eerstvolgende verzoek dicht zijn: een
geindexeerde query op `users.id` (of e-mail plus tenant) per verzoek.

**Twee accounttypen.** Een medewerkerstoken verwijst naar `users` (`is_active`). Een portaaltoken
(`aud == "portal"`, Foundation) verwijst naar `portal_users` (`is_blocked`): hetzelfde nummer in
de verkeerde tabel zou een portaalgebruiker op de status van een medewerker laten toetsen.

**Drie uitkomsten, geen twee.** `ONBEKEND` (database niet bereikbaar) is fail-closed: de ingang
weigert. Maar het is geen `UITGESCHAKELD`: de middleware antwoordt dan met een storing (503) en
niet met "uw account is uitgeschakeld", zodat een korte databasestoring niemand uitlogt.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from enum import Enum

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

#: Een gebruikers-id of e-mailadres uit `sub` is nooit langer; langer is geen echt account.
_MAX_SUBJECT_LENGTH = 320
#: Een id past in int4 (tot 2147483647); meer dan 9 cijfers is geen echt id en zou de database een
#: fout geven (503) in plaats van een weigering (401).
_MAX_ID_DIGITS = 9


def is_portal_token(payload: Mapping[str, object]) -> bool:
    """Is dit een portaaltoken (Foundation magic link, `aud == "portal"`, ook als lijst)?

    Een portaaltoken verwijst met `sub` naar `portal_users`, een medewerkerstoken naar `users`.
    De ene plek die dit vaststelt, voor de middleware en voor elke WebSocket-ingang.
    """
    audience = payload.get("aud")
    return audience == "portal" or (isinstance(audience, list) and "portal" in audience)


def _sessiemaker() -> "async_sessionmaker[AsyncSession] | None":
    """De sessiemaker voor de statusquery.

    Een eigen functie zodat een integratietest alleen DEZE controle naar zijn testverbinding kan
    omleiden, zonder `db_manager` te vervangen (dat gebruiken ook de auditschrijvers).
    """
    from src.core.database.database import db_manager

    return db_manager.async_session_maker


class AccountStatus(str, Enum):
    ACTIEF = "actief"
    UITGESCHAKELD = "uitgeschakeld"
    ONBEKEND = "onbekend"


async def _portaalgebruiker_is_actief(sessie: object, subject: str, tenant_id: int) -> bool:
    from sqlalchemy import select

    from src.core.database.bypass_session import adopt_tenant
    from src.core.models.foundation_content import PortalUser

    if not (subject.isascii() and subject.isdigit() and len(subject) <= _MAX_ID_DIGITS):
        return False
    assert isinstance(sessie, AsyncSession)
    # De tenant komt uit het GEVERIFIEERDE token, nooit uit invoer.
    async with adopt_tenant(sessie, tenant_id):
        geblokkeerd = (
            await sessie.execute(
                select(PortalUser.is_blocked).where(
                    PortalUser.id == int(subject), PortalUser.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
    return geblokkeerd is False


async def token_is_ingetrokken(payload: Mapping[str, object]) -> bool:
    """Is dit toegangstoken ingetrokken: zijn `jti` staat op de blacklist, of het is uitgegeven op of voor
    de laatste "alle sessies"-intrekking van de gebruiker (nieuw wachtwoord)?

    Voor de WebSocket-ingangen die een token zelf lezen (`websocket_auth.token_mag_op_een_websocket`): de
    HTTP-ingangen doen dit via `dependencies._weiger_als_ingetrokken`, maar de WebSocket-ingangen liepen
    daar niet langs (Gate 2, 2026-10-18). Fail-closed: een token zonder `jti` of een controle die niet kan
    worden uitgevoerd telt als ingetrokken.
    """
    from src.core.auth.oauth2_service import oauth2_service

    jti = payload.get("jti")
    if not jti:
        return True
    try:
        maker = _sessiemaker()
        if not maker:
            raise RuntimeError("Database not initialized")
        async with maker() as sessie:
            if await oauth2_service.is_jti_revoked(str(jti), sessie):
                return True
            sub = payload.get("sub")
            if isinstance(sub, str) and sub.isdigit() and len(sub) <= _MAX_ID_DIGITS:
                return await oauth2_service.is_uitgegeven_voor_intrekking(
                    int(sub), payload.get("iat"), sessie
                )
    except (SQLAlchemyError, RuntimeError, OSError, TimeoutError):
        logger.error(
            "tokenintrekking niet te controleren, ingang weigert (fail-closed)", exc_info=True
        )
        return True
    return False


#: Een e-mailadres uit `sub` hoort bij een vast id; dit is alleen het LABEL van een limietemmer, geen
#: autorisatie (die blijft zonder cache, zie boven). Verloopt na vijf minuten en blijft begrensd.
_ID_BIJ_EMAIL: dict[tuple[int, str], tuple[float, int]] = {}
_ID_BIJ_EMAIL_TTL_SECONDEN = 300.0
_ID_BIJ_EMAIL_MAX = 10_000


async def _zoek_id_bij_email(email: str, tenant_id: int) -> int | None:
    """Het gebruikers-id bij een e-mailadres binnen `tenant_id`, of `None`."""
    from sqlalchemy import select

    from src.core.database.bypass_session import pre_auth_lookup
    from src.core.models.rbac_models import User

    maker = _sessiemaker()
    if not maker:
        raise RuntimeError("Database not initialized")
    async with maker() as sessie:
        async with pre_auth_lookup(sessie) as opzoeker:
            return (
                await opzoeker.execute(
                    select(User.id).where(User.email == email, User.tenant_id == tenant_id)
                )
            ).scalar_one_or_none()


async def gebruikers_id_uit_sub(
    subject: str, tenant_id: int, *, portal: bool = False
) -> str | None:
    """Het NUMERIEKE gebruikers-id achter `sub`, of `None` als dat niet vast te stellen is.

    `sub` heeft twee vormen: het wachtwoordpad zet het e-mailadres erin, de andere inlogpaden het
    id (gemeten 2026-10-27: `auth_service.py` tegenover `oauth2_service.py`, `token_refresh.py`,
    `foundation/auth.py`). Een limiet die op de ruwe `sub` telt geeft een gebruiker twee emmers.

    Een portaaltoken verwijst naar `portal_users` en krijgt een eigen voorvoegsel, zodat portaal-id 5
    en medewerker-id 5 geen emmer delen. `None` bij een database die niet bereikbaar is of een
    e-mailadres dat bij geen account hoort: de aanroeper weigert dan (fail-closed).
    """
    if len(subject) > _MAX_SUBJECT_LENGTH:
        return None
    if subject.isascii() and subject.isdigit():
        if len(subject) > _MAX_ID_DIGITS:
            return None
        return f"{'p' if portal else 'u'}{int(subject)}"
    if portal:
        return None
    sleutel = (tenant_id, subject)
    nu = time.monotonic()
    bekend = _ID_BIJ_EMAIL.get(sleutel)
    if bekend is not None and nu - bekend[0] < _ID_BIJ_EMAIL_TTL_SECONDEN:
        return f"u{bekend[1]}"
    try:
        gevonden = await _zoek_id_bij_email(subject, tenant_id)
    except (SQLAlchemyError, RuntimeError, OSError, TimeoutError):
        logger.error(
            "gebruikers-id niet vast te stellen voor de limiet (tenant=%s)",
            tenant_id,
            exc_info=True,
        )
        return None
    if gevonden is None:
        return None
    if len(_ID_BIJ_EMAIL) >= _ID_BIJ_EMAIL_MAX:
        _ID_BIJ_EMAIL.clear()
    _ID_BIJ_EMAIL[sleutel] = (nu, gevonden)
    return f"u{gevonden}"


async def haal_account_status(
    subject: str, tenant_id: int, *, portal: bool = False
) -> AccountStatus:
    """De status van het account in `subject` (id of e-mail uit `sub`) binnen `tenant_id`.

    `portal=True` voor een portaaltoken (`aud == "portal"`): dan telt `portal_users.is_blocked`.
    """
    from src.core.auth.auth_service import auth_service

    try:
        maker = _sessiemaker()
        if not maker:
            raise RuntimeError("Database not initialized")
        async with maker() as sessie:
            if portal:
                actief = await _portaalgebruiker_is_actief(sessie, subject, tenant_id)
            else:
                actief = await auth_service.account_is_active(sessie, subject, tenant_id)
    except (SQLAlchemyError, RuntimeError, OSError, TimeoutError):
        # Het onderwerp (kan een e-mailadres zijn) komt bewust NIET in het log.
        logger.error(
            "accountstatus niet te controleren, ingang weigert (fail-closed, tenant=%s)",
            tenant_id,
            exc_info=True,
        )
        return AccountStatus.ONBEKEND
    return AccountStatus.ACTIEF if actief else AccountStatus.UITGESCHAKELD
