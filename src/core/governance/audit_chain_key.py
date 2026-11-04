"""De HMAC-sleutel voor de auditketen (ADR-036 OP-120).

**Waarom de keten gesleuteld wordt.** `_compute_hash` was kale SHA-256 over kolommen die in
dezelfde rij staan. Wie schrijfrechten op `audit_logs` heeft kon een regel vervalsen en de hele
keten herberekenen; gemeten: `is_valid=True` na een volledige hercompute. Met een HMAC verschuift
de drempel van "kan de tabel schrijven" naar "kan de tabel schrijven EN de sleutel lezen".

**Waar dat WEL en NIET tegen helpt** -- eerlijk, want dit is precies waar ADR-019 de mist in ging:

- WEL: een gestolen `DATABASE_URL`, een databasedump, een backup, een DBA zonder deploy-rechten,
  en een gecompromitteerde ActivePieces-flow (die deelt de databasegebruiker maar krijgt deze
  sleutel niet).
- NIET: codeuitvoering in de applicatie zelf. Sleutel en databaseverbinding zitten in hetzelfde
  procesgeheugen. Dat is geen omissie van deze module maar een eigenschap van het ontwerp, en het
  staat zo in ADR-019 onder "Wat tamper-evident hier WEL en NIET betekent".

**Een EIGEN sleutel, niet `TOOL_PAYLOAD_PSEUDONYM_KEY` hergebruiken.** Ander doel, andere
levensduur, andere blootstelling. Die sleutel mag bovendien nooit roteren omdat hij de
koppelbaarheid van pseudoniemen draagt; deze mag dat wel, mits met een knippunt (zie
`chain_epoch_id` in `audit_chain_anchors`). Ze koppelen zou die vrijheid weggooien.

**De prijs, en die hoort in de ADR.** Een externe auditor kan de keten niet meer narekenen zonder
de productiesleutel. Dat is de tegenhanger van `hitl_evidence.py`, waar de digest juist BEWUST
ongesleuteld is zodat een auditor hem wel kan narekenen. Die twee horen dus niet
"geharmoniseerd" te worden -- ze beantwoorden een andere vraag.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import threading

from src.core.tool_broker.redaction import (
    EPHEMERAL_KEY_ENVIRONMENTS,
    key_strength_problem,
)

logger = logging.getLogger(__name__)

KEY_ENV_VAR = "AUDIT_CHAIN_HMAC_KEY"

#: Eigen domein, gescheiden van de pseudonimiseringssleutel. `:v1` omdat dit de eerste
#: gesleutelde vorm is; een wijziging in de AFLEIDING vraagt een bump naar `:v2` plus een nieuw
#: knippunt, precies zoals `redaction.py` dat voor `:v2` heeft vastgelegd.
_HMAC_DOMAIN = b"sanskritisetu:audit-chain:v1"

#: De naam die in de kolom `audit_logs.hash_algorithm` komt te staan. `NULL` betekent legacy
#: SHA-256. Deze waarde zit ZELF in de preimage -- anders zet een aanvaller hem terug op `NULL`
#: en rekent sleutelloos opnieuw uit.
ALGORITHM_NAME = "hmac-sha256-v1"

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DERIVED_KEY_BYTES = 32

_key_lock = threading.Lock()
_cached_key: bytes | None = None


def _environment() -> str:
    """Uit `os.environ` en niet uit settings.

    `get_settings().environment` heeft `development` als default, dus een vergeten `ENVIRONMENT`
    zou stil in ephemere modus vallen -- in productie. Zelfde reden als in `redaction.py`.
    """
    return os.environ.get("ENVIRONMENT", "development").strip().lower()


def _allows_ephemeral_key() -> bool:
    """Een TOELAATLIJST, geen blokkeerlijst.

    De vloot draait ook `staging`, `blue` en `green`, en blue/green is een productietechniek.
    Met een blokkeerlijst op alleen "production" vielen die stil open op een per-proces sleutel --
    en dan verifieert geen enkele keten meer na een herstart.
    """
    return _environment() in EPHEMERAL_KEY_ENVIRONMENTS


def reset_key_cache() -> None:
    """Alleen bedoeld voor tests."""
    global _cached_key
    with _key_lock:
        _cached_key = None


def audit_chain_key() -> bytes:
    """De afgeleide sleutel, of een harde fout buiten een ontwikkelomgeving."""
    global _cached_key

    with _key_lock:
        if _cached_key is not None:
            return _cached_key

        configured = os.environ.get(KEY_ENV_VAR) or None

        if configured is not None:
            probleem = key_strength_problem(configured)
            if probleem is not None:
                raise RuntimeError(f"{KEY_ENV_VAR} is te zwak: {probleem}")

            # VASTE salt. Een willekeurige salt maakt de afleiding per proces anders, en dan
            # verifieert dezelfde rij na een worker-recycle (ADR-011) niet meer -- dat leest als
            # manipulatie terwijl er niets is gebeurd. De salt scheidt domeinen; de sleutel doet
            # het geheime werk.
            _cached_key = hashlib.scrypt(
                configured.encode("utf-8"),
                salt=_HMAC_DOMAIN,
                n=_SCRYPT_N,
                r=_SCRYPT_R,
                p=_SCRYPT_P,
                dklen=_DERIVED_KEY_BYTES,
            )
            return _cached_key

        if not _allows_ephemeral_key():
            raise RuntimeError(
                f"{KEY_ENV_VAR} is niet gezet en omgeving '{_environment()}' staat geen ephemere "
                "sleutel toe. Zonder sleutel is de auditketen niet te ondertekenen, en een kale "
                "SHA-256 is geen alternatief: die is door iedereen met schrijfrechten op de "
                "tabel te herberekenen (ADR-036 OP-120)."
            )

        # Buiten productie een sleutel per proces. Gevolg: ketens verifieren niet over een
        # herstart heen. Dat is in een ontwikkelomgeving het juiste compromis -- daar is geen
        # bewijswaarde -- maar het is bewust luidruchtig.
        logger.warning(
            "%s is niet gezet; buiten productie wordt een per-proces sleutel gebruikt. "
            "Ketens verifieren daardoor NIET over een herstart heen.",
            KEY_ENV_VAR,
        )
        _cached_key = secrets.token_bytes(_DERIVED_KEY_BYTES)
        return _cached_key


def hmac_is_configured() -> bool:
    """Is er een ECHTE sleutel? Bepaalt of de schrijvers omschakelen (ADR-036 OP-120).

    Bewust NIET `audit_chain_key()` aanroepen en op een fout wachten. Twee redenen:

    1. **Zonder deze controle degradeert alles stil.** Buiten een ontwikkelomgeving gooit
       `audit_chain_key()` een `RuntimeError` als de sleutel ontbreekt. `log_event` vangt elke
       fout op en schrijft de rij dan ZONDER hash weg (degraded mode). Zou een schrijver
       onvoorwaardelijk omschakelen voordat de sleutel gewired is, dan belandt elke auditregel
       ongehasht in de tabel -- erger dan de toestand van voor de omschakeling.
    2. **De ephemere sleutel mag niet voor de keten gebruikt worden.** Die is per proces anders,
       dus dezelfde rij verifieert na een worker-recycle (ADR-011) niet meer. Dat leest als
       manipulatie terwijl er niets is gebeurd. Voor pseudonimisering is een ephemere sleutel in
       development acceptabel; voor een keten die over de tijd moet kloppen niet.

    **Is dit fail-open?** Gedeeltelijk, en bewust. Wie de omgevingsvariabele wegneemt zet nieuwe
    rijen terug op sleutelloze SHA-256. Precies daarvoor bestaat het knippunt: een rij NA
    `chain_epoch_id` zonder markering is een afwijking, ook als de hash klopt. De degradatie is
    dus zichtbaar in plaats van stil.
    """
    return bool(os.environ.get(KEY_ENV_VAR))


def mark_entry(entry: object) -> None:
    """Zet `hash_algorithm` op de auditregel, maar alleen als er een sleutel is.

    Moet VOOR het hashen worden aangeroepen: `_compute_hash` leest de markering om te bepalen
    welk algoritme het gebruikt.
    """
    if not hmac_is_configured():
        return

    # Sterkte nu al toetsen, niet pas bij het hashen. Anders staat de markering er wel en faalt
    # het hashen daarna -- dan is de rij als gesleuteld gemarkeerd zonder gesleutelde hash.
    audit_chain_key()

    entry.hash_algorithm = ALGORITHM_NAME  # type: ignore[attr-defined]


def chain_mac(preimage: str) -> str:
    """De gesleutelde ketenhash over een canonieke preimage.

    Geeft 64 hex-tekens, net als de SHA-256 die hij vervangt -- `audit_hash` is `String(64)` en
    hoeft dus niet te worden verbreed.
    """
    import hmac

    return hmac.new(
        audit_chain_key(),
        _HMAC_DOMAIN + b":" + preimage.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
