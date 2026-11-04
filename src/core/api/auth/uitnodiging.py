"""Een nieuwe medewerker uitnodigen: eenmalige link om zelf een wachtwoord te kiezen (2026-10-15).

De beheerder voert alleen e-mail en rol in. De medewerker krijgt een mail met een link; via die link
kiest hij zelf een wachtwoord. Er is GEEN nieuwe tabel: de link is hetzelfde token als bij "wachtwoord
vergeten" (Redis, sleutel `password_reset:<token>`, waarde het gebruikers-id) en de route die hem
inwisselt is dezelfde (`POST /api/v1/auth/reset-password`, eenmalig, het token wordt na gebruik
gewist). Het enige verschil is de geldigheid: 48 uur in plaats van een uur.

Veiligheid: het token is `secrets.token_urlsafe(32)` en staat nergens in een log; het gebruikers-id
komt uit de aanmaakroute en niet uit een verzoek; de nieuwe gebruiker heeft een willekeurig, onbekend
startwachtwoord (zie `users_list_router.create_user`), dus zonder de link kan niemand inloggen.
"""

from __future__ import annotations

import logging

from src.core.config.frontend_url import FrontendUrlOntbreekt, frontend_url

from .dependencies import bouw_uitnodiging, get_email_service, get_redis_client
from .router_password import geef_resettoken_uit

logger = logging.getLogger(__name__)

#: Gelijk aan `UITNODIGING_GELDIG_UREN` in `services/email.py` (dat staat in de mailtekst).
UITNODIGING_GELDIG_SECONDEN = 48 * 3600


async def stuur_uitnodiging(email: str, user_id: int) -> bool:
    """Geef een eenmalig token uit en mail de link; geeft terug of de mail is verstuurd.

    Een mislukte mail breekt het aanmaken niet af (de gebruiker bestaat al), maar is NIET stil: het log
    krijgt een ERROR (zonder adres of link) en de aanroeper krijgt `False`, zodat de beheerder het ziet.
    """
    try:
        basis = frontend_url()
    except FrontendUrlOntbreekt:
        # Zonder dit gaat er een link naar localhost de deur uit: de medewerker kan er niets mee. Het opstarten weigert
        # al zonder FRONTEND_URL buiten een zachte omgeving; dit vangt een waarde die daarna is verdwenen of ongeldig is.
        logger.error("invitation_frontend_url_missing: user_id=%s", user_id)
        return False
    try:
        redis_client = await get_redis_client()
        token = await geef_resettoken_uit(redis_client, user_id, UITNODIGING_GELDIG_SECONDEN)
        link = f"{basis}/reset-password?token={token}"
        gelukt = await get_email_service().send(bouw_uitnodiging(email, link))
    except Exception as exc:
        # Alleen het soort fout, geen tekst en geen traceback: de melding van een mailserver kan het
        # ontvangersadres bevatten (Gate 2 security, 2026-10-15).
        logger.error("invitation_email_failed: user_id=%s: %s", user_id, type(exc).__name__)
        return False
    if not gelukt:
        logger.error("invitation_email_not_sent: user_id=%s", user_id)
    return bool(gelukt)
