"""Versleuteling van KLANTSLEUTELS, met een aparte sleutel per tenant.

**Waarom dit niet `scheduling/integrations/token_encryption.py` hergebruikt.** Dat object doet
echte Fernet en is op zichzelf goed geschreven, maar het heeft drie eigenschappen die voor
klantsleutels niet kunnen:

1. **Het valt stil terug op een proces-lokale sleutel.** Ontbreekt `MASTER_ENCRYPTION_KEY`, dan
   gebruikt het `secrets.token_hex(32)` uit een module-constante -- een andere sleutel per
   proces. Gemeten 2026-09-20: die variabele stond toen in NUL van `.env.example`,
   `docker-compose.yml` en `docker-compose.prod.yml`. Inmiddels staat hij in de twee
   compose-bestanden (`:-` lokaal, `:?` in productie); `.env.example` is niet nagekeken, want
   dat pad valt onder een denyregel. De TERUGVAL in `token_encryption.py` is er nog, dus het
   stille pad bestaat nog steeds -- een gezette variabele maakt alleen de kans kleiner dat hij
   aanslaat. Gevolg: onleesbaar na een herstart, en onleesbaar tussen de
   gunicorn-workers onderling. Voor een OAuth-token is dat vervelend (opnieuw koppelen); voor
   een sleutel die een klant ons heeft gegeven is het stil gegevensverlies.
   Die bevinding heeft een eigen brief:
   `docs/agent-briefs/generated/2026-09-20-bevinding-agenda-tokens-onleesbaar-na-herstart.md`.
2. **Een gedeelde afgeleide sleutel voor alle tenants.** Wie hem te pakken krijgt, opent de
   sleutels van elke klant. De gangbare praktijk voor klantgeheimen in multi-tenant SaaS is
   scheiding per tenant (envelope-encryptie met een sleutel per tenant); dit haalt hetzelfde
   effect zonder dat er een sleutelkluis bij hoeft.
3. **Een zout dat bij de agenda hoort** (`sha256(b"sanskritisetu_calendar_tokens")`). Dat
   hergebruiken zou twee domeinen aan dezelfde afgeleide sleutel hangen.

**Wat dit WEL is, en wat niet.** Dit is geen zelfgebouwde cryptografie: HKDF en Fernet komen
allebei uit `cryptography` en worden hier gebruikt waarvoor ze bedoeld zijn. Wat het niet is:
een vervanging voor een sleutelkluis. De hoofdsleutel leeft in de omgeving, dus wie de server
heeft, heeft de sleutels. Dat is inherent aan opslag aan onze kant en hoort zo in het
inrichtingsdossier te staan -- niet weggeschreven als "versleuteld, dus veilig".
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

#: Eigen domeinzout. Bewust NIET dat van de agenda-tokens: twee domeinen horen niet aan
#: dezelfde afgeleide sleutel te hangen.
_ZOUT = hashlib.sha256(b"sanskritisetu_tenant_llm_provider_keys").digest()

#: Voorvoegsel van de HKDF-context. De tenant komt erachter, zodat elke tenant een eigen
#: sleutel krijgt uit dezelfde hoofdsleutel.
_CONTEXT_VOORVOEGSEL = b"tenant-llm-provider:"

#: De versie die `encrypt` voor de ciphertext zet. Zonder zo'n aanduiding is een rotatie van
#: `MASTER_ENCRYPTION_KEY` stil gegevensverlies -- precies de faalvorm die deze module komt
#: oplossen, alleen verplaatst van "herstart" naar "rotatie" (Gate 2-bevinding 2026-09-20).
_HUIDIGE_VERSIE = "v1"

#: Minimaal aantal BYTES willekeur na decodering. 32 is de sleutellengte die Fernet gebruikt;
#: minder aanvoeren dan je eruit haalt, heeft geen zin.
_MINIMALE_SLEUTELBYTES = 32

#: Minimaal aantal VERSCHILLENDE bytewaarden in dat materiaal. 32 willekeurige bytes hebben er
#: gemiddeld ongeveer 30; onder de 16 komen is in de praktijk uitgesloten. Een herhaald patroon
#: zoals `"a" * 43` decodeert naar drie verschillende waarden en valt hier dus uit -- en dat is
#: precies het geval dat een lengte-eis alleen niet ziet (Gate 2-meting 2026-09-20).
_MINIMALE_UNIEKE_BYTES = 16

#: Minimaal aantal HOOFDLETTERS in de base64-vorm. Alleen op die tak: `secrets.token_hex`
#: levert kleine letters en zou hier anders altijd op afketsen. Gemeten over 20.000 verse
#: `token_urlsafe(32)`-waarden: NUL hadden er minder dan twee.
_MINIMALE_HOOFDLETTERS = 2

#: De vaste hoofdsleutel van de testomgeving (`tests/conftest.py`, constante `_TEST_MASTER_ENCRYPTION_KEY`).
#: Hij staat in de repo en is dus voor iedereen bekend; een omgeving die hem gebruikt versleutelt klantsleutels
#: met een publieke sleutel. Daarom wordt PRECIES deze waarde geweigerd buiten een testomgeving.
#: Een test houdt deze constante gelijk aan die in conftest.
BEKENDE_TESTSLEUTEL = "w0PW8Vh4-UPi70LUTf0Gam8DD7Dc2PAo8x4YO-Y_eMQ"

#: Omgevingen waarin de testsleutel is toegestaan. Dezelfde fail-closed lijst als `ZACHTE_OMGEVINGEN` in
#: `src/core/database/applicatierol_controle.py` -- hier gekopieerd en NIET geimporteerd, want security ->
#: database zou een nieuwe laagrand zijn. Een test houdt de twee lijsten gelijk. Een onbekende of verkeerd
#: gespelde naam (`prod`, `live`, een lege waarde) is streng.
_ZACHTE_OMGEVINGEN = frozenset({"development", "dev", "local", "test", "testing"})


class OnbekendeSleutelversie(ValueError):
    """De opgeslagen tekst draagt een versie die deze code niet kent."""


class HoofdsleutelOntbreekt(RuntimeError):
    """`MASTER_ENCRYPTION_KEY` is niet gezet.

    Dit is met opzet een harde fout en geen waarschuwing met terugval. Een terugvalsleutel
    maakt opgeslagen klantsleutels onleesbaar zodra het proces herstart -- en dat merk je pas
    als een klant belt. Een applicatie die weigert te starten is luidruchtig, en luidruchtig is
    hier het goede gedrag.
    """


class HoofdsleutelTeZwak(HoofdsleutelOntbreekt):
    """De hoofdsleutel is gezet maar bevat te weinig willekeur.

    Erft van `HoofdsleutelOntbreekt` zodat elke aanroeper die "geen bruikbare sleutel" al
    afvangt -- de 503 in de router -- dit geval meteen meepakt. Voor de gebruiker is het
    dezelfde situatie: er is niets om veilig mee te versleutelen.

    **Waarom dit een eigen controle nodig heeft.** HKDF is een sleutel-AFLEIDING, geen
    sleutel-VERSTERKING: er zit geen werkfactor in. Wordt `MASTER_ENCRYPTION_KEY` een
    wachtwoordzin, dan is elke opgeslagen klantsleutel offline te kraken met een
    woordenboekaanval, en HKDF vertraagt dat met niets. Een Gate 2-reviewer mat dat
    `TenantSecretEncryption(master_key="x")` gewoon versleutelde. Het antwoord is niet een
    derde KDF erbij (dat zou een PBKDF2-ronde per verzoek kosten) maar eisen dat de sleutel is
    zoals hij hoort: voortgebracht door een generator, niet bedacht door een mens.
    """


class HoofdsleutelIsTestsleutel(HoofdsleutelOntbreekt):
    """De hoofdsleutel is de vaste testsleutel uit de repo, en de omgeving is geen testomgeving.

    Erft van `HoofdsleutelOntbreekt`, net als `HoofdsleutelTeZwak`: voor elke aanroeper is er geen bruikbare
    sleutel, en de 503 in de router pakt dit dan meteen mee.
    """


def _ontcijfer_hoofdsleutel(ruw: str) -> bytes:
    """Zet de omgevingswaarde om naar sleutelmateriaal, of weiger hem.

    Toegestaan zijn de twee vormen die een generator voortbrengt: urlsafe-base64
    (`secrets.token_urlsafe(32)`) en hexadecimaal (`secrets.token_hex(32)`).

    **Wat deze controle WEL en NIET doet -- nagemeten, niet beredeneerd.** De eerste versie
    beweerde hier dat "een vrij gekozen wachtwoordzin geweigerd wordt, en dat is het doel".
    Dat was onwaar, en een Gate 2-reviewer mat het: `base64.urlsafe_b64decode` draait standaard
    met `validate=False` en gooit tekens buiten het alfabet -- spaties, leestekens -- STIL weg.
    Elke zin van ongeveer 43 bruikbare tekens decodeerde daarmee naar 32 bytes en passeerde,
    inclusief `"correct horse battery staple ..."`. Het was dus een LENGTE-controle met een
    sterkte-claim erboven.

    Nu zijn er drie zeven, en samen vangen ze meer dan lengte alleen:

    1. `validate=True` -- een waarde met spaties of leestekens valt er nu uit in plaats van
       stilzwijgend te worden uitgedund;
    2. de gedecodeerde bytes moeten minstens `_MINIMALE_UNIEKE_BYTES` verschillende waarden
       bevatten. Dat vangt de herhaalde waarde die eis 1 niet kan zien: `"a" * 43` is geldige
       base64 en decodeert naar 32 bytes met DRIE verschillende waarden;
    3. de base64-vorm moet hoofdletters bevatten. Die derde zeef is er omdat de eerste twee
       een Nederlandse wachtwoordzin met koppeltekens nog steeds doorlieten -- gemeten, niet
       bedacht. Zie de toelichting in de code voor waarom het hoofdletters zijn en geen
       cijfers.

    **Dit is geen entropiemeter en het pretendeert dat niet.** Het vangt een typefout, een te
    korte waarde, een zin en een herhaald patroon. Een mens die zijn best doet om iets te
    verzinnen dat er willekeurig uitziet, komt er nog steeds langs. De echte bescherming is de
    generator, en die staat in de foutmelding.
    """
    tekst = ruw.strip()
    ontcijferd = b""
    try:
        # `b64decode(..., validate=True)` en NIET `urlsafe_b64decode`: die laatste kent de
        # parameter `validate` niet en dunt de invoer dus stil uit. `altchars` maakt hem
        # alsnog urlsafe, zodat `-` en `_` uit `token_urlsafe` gewoon werken.
        ontcijferd = base64.b64decode(
            tekst + "=" * (-len(tekst) % 4), altchars=b"-_", validate=True
        )
        if sum(teken.isupper() for teken in tekst) < _MINIMALE_HOOFDLETTERS:
            # De derde zeef, en hij vangt wat de eerste twee lieten lopen: een Nederlandse
            # wachtwoordzin met koppeltekens is geldige base64 EN gevarieerd genoeg. Gemeten
            # 2026-09-20: `"dit-is-mijn-wachtwoordzin-voor-de-sanskritisetu-hoofdsleutel"`
            # passeerde die twee.
            #
            # Waarom hoofdletters en GEEN cijfers, hoewel dat laatste sterker lijkt: gemeten
            # over 20.000 verse `token_urlsafe(32)`-waarden heeft 0,62% er minder dan twee
            # cijfers in, en 0 van de 20.000 minder dan twee hoofdletters. Een cijfer-eis zou
            # dus ongeveer een op de 160 echte sleutels weigeren -- een storing die pas bij de
            # zoveelste uitrol opduikt en nergens naar te herleiden is.
            ontcijferd = b""
    except (ValueError, binascii.Error):
        ontcijferd = b""
    if not _is_bruikbaar(ontcijferd):
        try:
            ontcijferd = bytes.fromhex(tekst)
        except ValueError:
            ontcijferd = b""
    if _is_bruikbaar(ontcijferd):
        return ontcijferd
    raise HoofdsleutelTeZwak(
        "MASTER_ENCRYPTION_KEY is gezet maar is niet bruikbaar als sleutel. Verwacht wordt "
        f"minstens {_MINIMALE_SLEUTELBYTES} bytes met minstens {_MINIMALE_UNIEKE_BYTES} "
        "verschillende waarden, in urlsafe-base64 of hex. Genereer hem met "
        "secrets.token_urlsafe(32). Een zelfbedachte wachtwoordzin hoort hier niet, omdat HKDF "
        "geen werkfactor heeft: die zou elke opgeslagen klantsleutel offline kraakbaar maken."
    )


def _is_bruikbaar(materiaal: bytes) -> bool:
    """Lang genoeg EN gevarieerd genoeg.

    De drempel op het aantal verschillende bytes is ruim onder wat een generator oplevert:
    32 willekeurige bytes hebben er gemiddeld ongeveer 30 verschillende, en onder de 16 komen
    is in de praktijk uitgesloten. Een herhaalde waarde haalt hem nooit.
    """
    return (
        len(materiaal) >= _MINIMALE_SLEUTELBYTES and len(set(materiaal)) >= _MINIMALE_UNIEKE_BYTES
    )


#: Het sleutelmateriaal van `BEKENDE_TESTSLEUTEL`, op dezelfde manier ontcijferd als elke andere hoofdsleutel.
_BEKENDE_TESTSLEUTEL_MATERIAAL = _ontcijfer_hoofdsleutel(BEKENDE_TESTSLEUTEL)


def _als_hex(tekst: str) -> bytes:
    """De hex-lezing van een tekst, of leeg als het geen hex is."""
    try:
        return bytes.fromhex(tekst.strip())
    except ValueError:
        return b""


class TenantSecretEncryption:
    """Versleutelt en ontsleutelt een geheim, met een eigen sleutel per tenant."""

    def __init__(self, master_key: str | None = None) -> None:
        ruw = master_key or os.getenv("MASTER_ENCRYPTION_KEY")
        if not ruw or not ruw.strip():
            raise HoofdsleutelOntbreekt(
                "MASTER_ENCRYPTION_KEY is niet gezet. Zonder hoofdsleutel worden opgeslagen "
                "klantsleutels onleesbaar bij de eerstvolgende herstart, en dat is stil "
                "gegevensverlies. Zet de variabele in de omgeving; er is met opzet geen "
                "terugvalsleutel."
            )
        # Eerst ontcijferen, dan vergelijken op SLEUTELMATERIAAL en niet op tekst (uitrol-nazorg-3): dezelfde
        # bytes met extra `=`-opvulling, als hex of in het standaard-base64-alfabet is dezelfde sleutel en
        # werkt ook als sleutel, maar was met `ruw.strip() == BEKENDE_TESTSLEUTEL` niet herkend. Een niet te
        # ontcijferen waarde valt hier onder de bestaande foutroute (`HoofdsleutelTeZwak`).
        materiaal = _ontcijfer_hoofdsleutel(ruw)
        omgeving = os.getenv("ENVIRONMENT", "").strip().lower()
        # Ook de HEX-lezing van dezelfde tekst: `_ontcijfer_hoofdsleutel` probeert base64 eerst, en hex met twee of
        # meer hoofdletters is dan geldige base64 van een ANDER aantal bytes. Die sleutel is niet de testsleutel,
        # maar de tekst IS de hex van de testsleutel; die omweg sluiten we hier.
        is_testsleutel = materiaal == _BEKENDE_TESTSLEUTEL_MATERIAAL or _als_hex(ruw) == (
            _BEKENDE_TESTSLEUTEL_MATERIAAL
        )
        if is_testsleutel and omgeving not in _ZACHTE_OMGEVINGEN:
            raise HoofdsleutelIsTestsleutel(
                "MASTER_ENCRYPTION_KEY is de vaste testsleutel uit de repo, en deze omgeving is geen "
                "testomgeving. Die sleutel is voor iedereen bekend; genereer een eigen sleutel met "
                '`python -c "import secrets; print(secrets.token_urlsafe(32))"` en zet die.'
            )
        self._hoofdsleutel = materiaal

    def _fernet(self, tenant_id: int) -> Fernet:
        """De sleutel van EEN tenant, afgeleid uit de hoofdsleutel.

        HKDF met de tenant in het `info`-veld: dezelfde hoofdsleutel, een andere sleutel per
        tenant. Een lek van de afgeleide sleutel van tenant A opent tenant B niet.
        """
        if not isinstance(tenant_id, int) or isinstance(tenant_id, bool) or tenant_id <= 0:
            # Zonder deze controle zou `False` als tenant 0 doorgaan en zouden twee tenants
            # stilzwijgend dezelfde sleutel kunnen delen.
            raise ValueError("tenant_id moet een positief geheel getal zijn")

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_ZOUT,
            info=_CONTEXT_VOORVOEGSEL + str(tenant_id).encode("ascii"),
        )
        return Fernet(base64.urlsafe_b64encode(hkdf.derive(self._hoofdsleutel)))

    def encrypt(self, tenant_id: int, plaintext: str) -> str:
        """Versleutel een geheim voor deze tenant, met een versie-aanduiding ervoor."""
        rauw = self._fernet(tenant_id).encrypt(plaintext.encode("utf-8")).decode("ascii")
        return f"{_HUIDIGE_VERSIE}:{rauw}"

    def decrypt(self, tenant_id: int, ciphertext: str) -> str:
        """Ontsleutel een geheim van deze tenant.

        Gooit `InvalidToken` als de tekst beschadigd is OF als hij van een andere tenant komt.
        Die twee zijn hier met opzet niet te onderscheiden: het antwoord op allebei is
        "dit geheim is niet van jou".

        Een onbekende versie geeft `OnbekendeSleutelversie` en nadrukkelijk GEEN `InvalidToken`.
        Dat onderscheid is het halve werk bij een toekomstige rotatie: "beschadigd" en "met een
        sleutel van voor de rotatie versleuteld" vragen om verschillende antwoorden, en als ze
        dezelfde fout geven valt er geen migratiescript te schrijven dat weet welke rijen het
        moet aanpakken.
        """
        versie, _, rauw = ciphertext.partition(":")
        if versie != _HUIDIGE_VERSIE or not rauw:
            raise OnbekendeSleutelversie(
                "onbekende of ontbrekende sleutelversie in de opgeslagen tekst (verwacht "
                f"'{_HUIDIGE_VERSIE}:'); deze rij is met een ander formaat of een andere "
                "sleutel versleuteld en vraagt om een migratie, niet om een herstelpoging"
            )
        return self._fernet(tenant_id).decrypt(rauw.encode("ascii")).decode("utf-8")


__all__ = [
    "HoofdsleutelOntbreekt",
    "HoofdsleutelTeZwak",
    "InvalidToken",
    "OnbekendeSleutelversie",
    "TenantSecretEncryption",
]
