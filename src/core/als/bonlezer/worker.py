"""De bonlezer-worker: een Dramatiq-actor die een bon uit de uploadmap van een tenant leest (dag 2).

De backend maakt een opdracht `lees_bon(tenant_id, bestand_id)`, met de tenant uit de JWT van de aanvrager
(nooit uit het bestand of de bestandsnaam). Deze worker draait in een EIGEN image zonder uitgaand
netwerk behalve Redis (`Dockerfile`-doel `bonlezer-worker`, dienst `bonlezer-worker` in
`docker-compose.yml`): Docling en torch horen niet in het backend-image.

Wat de verwerking doet, en waarom zo:

- **Alleen de eigen tenant.** Het pad wordt ZELF opgebouwd uit twee gevalideerde delen:
  `<uploadmap>/<tenant_id>/<bestand_id>`. `tenant_id` is een positief geheel getal, `bestand_id` is
  32 kleine hexadecimale tekens en een extensie uit een vaste lijst; een naam van een gebruiker, een
  `..` of een scheidingsteken komt er niet doorheen. Een bestand van een andere tenant of een bestand
  dat er niet is, geeft DEZELFDE uitkomst (geen bestaan prijsgeven).
- **Geen symlinks.** De tenantmap en het bestand worden eerst met `lstat` bekeken (een symlink of
  koppelpunt wordt geweigerd), het bestand wordt geopend met `O_NOFOLLOW` waar het besturingssysteem dat
  kent, en daarna wordt de geopende descriptor met `fstat` vergeleken met de `lstat` van daarvoor.
- **Een keer lezen (TOCTOU).** De bytes worden EEN keer uit de geopende descriptor gelezen, gehasht en in
  een privekopie (een tijdelijke map, rechten 0600) gezet. De lezer krijgt die kopie; een wijziging van
  het upload-bestand na het lezen bereikt hem niet.
- **Geen bontekst in log of resultaat.** Het resultaat bevat status, reden, sha256 en de velden. Een
  onverwachte fout geeft alleen de NAAM van het fouttype en wordt zonder traceback gelogd: de melding
  van een uitzondering kan tekst van de bon bevatten. (De regel uit `backend-patterns.md` om met
  `exc_info=True` te loggen wijkt hier bewust af; privacy van de bon gaat voor.)

Wat dit NIET doet: de uitkomst opslaan (geen tabel, geen migratie; het resultaat gaat via de
resultaatopslag van Dramatiq in Redis, met een korte bewaartijd) en geen upload-route (dag 3).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import stat
import tempfile
import time
from pathlib import Path
from typing import Protocol, cast

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import Middleware, TimeLimit
from dramatiq.results import Results
from dramatiq.results.backends import RedisBackend

from src.core.noodstop import model_deur  # noqa: F401  (opstartpunt: meldt de noodstopcontrole van de modeldeur aan)
from src.core.als.bonlezer.lezer import MAX_BYTES, BonLezer, OngeldigBestand
from src.core.als.bonlezer.veldenlaag import BonVelden, lees_velden

logger = logging.getLogger(__name__)

QUEUE = "bonlezer"
STANDAARD_UPLOADMAP = "/data/bonnen"
STANDAARD_MODELLEN = "/modellen"

#: 32 kleine hexadecimale tekens en een extensie die de lezer kent. Dit is de ENIGE vorm van een
#: bestandsnummer die de worker aanvaardt; de backend maakt het zelf aan (dag 3), er komt geen naam
#: van een gebruiker in.
_BESTAND_ID = re.compile(r"[0-9a-f]{32}\.(?:pdf|png|jpg|jpeg|tif|tiff|bmp)")

#: Windows: een koppelpunt of symlink heeft dit kenmerk; `S_ISLNK` ziet niet elk koppelpunt.
_REPARSE_POINT = 0x400

_NIET_GEVONDEN = "bestand niet gevonden"


class _Lezer(Protocol):
    def lees(self, pad: Path) -> str: ...


class _Geweigerd(Exception):
    """De opdracht of het bestand wordt geweigerd; `reden` is de tekst voor het resultaat."""


def upload_root() -> Path:
    return Path(os.environ.get("BONLEZER_UPLOAD_ROOT", STANDAARD_UPLOADMAP))


# -- het bestand veilig openen -------------------------------------------------------------------


def _is_koppeling(status: os.stat_result) -> bool:
    return stat.S_ISLNK(status.st_mode) or bool(
        getattr(status, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _controleer_opdracht(tenant_id: object, bestand_id: object) -> tuple[int, str]:
    if not isinstance(tenant_id, int) or isinstance(tenant_id, bool) or tenant_id <= 0:
        raise _Geweigerd("ongeldige opdracht")
    if not isinstance(bestand_id, str) or not _BESTAND_ID.fullmatch(bestand_id):
        raise _Geweigerd("ongeldige opdracht")
    return tenant_id, bestand_id


def _open_bestand(root: Path, tenant_id: int, bestand_id: str) -> int:
    """Open `<root>/<tenant_id>/<bestand_id>` zonder een koppeling te volgen; geef de descriptor."""
    tenantmap = root / str(tenant_id)
    pad = tenantmap / bestand_id
    try:
        map_status = os.lstat(tenantmap)
        if _is_koppeling(map_status) or not stat.S_ISDIR(map_status.st_mode):
            raise _Geweigerd(_NIET_GEVONDEN)
        voor = os.lstat(pad)
        if _is_koppeling(voor) or not stat.S_ISREG(voor.st_mode):
            raise _Geweigerd(_NIET_GEVONDEN)
        vlaggen = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        beschrijver = os.open(pad, vlaggen)
    except OSError as fout:
        raise _Geweigerd(_NIET_GEVONDEN) from fout
    try:
        na = os.fstat(beschrijver)
        if not stat.S_ISREG(na.st_mode):
            raise _Geweigerd(_NIET_GEVONDEN)
        if na.st_size > MAX_BYTES:
            raise _Geweigerd(_NIET_GEVONDEN)  # zelfde tekst: de grootte verraadt anders het bestaan
        if voor.st_ino and na.st_ino and (voor.st_dev, voor.st_ino) != (na.st_dev, na.st_ino):
            raise _Geweigerd(_NIET_GEVONDEN)  # het bestand is tussen kijken en openen verwisseld
    except BaseException:
        os.close(beschrijver)
        raise
    return beschrijver


def _lees_bytes(beschrijver: int) -> bytes:
    with os.fdopen(beschrijver, "rb") as bestand:
        gegevens = bestand.read(MAX_BYTES + 1)
    if len(gegevens) > MAX_BYTES:
        raise _Geweigerd(_NIET_GEVONDEN)
    return gegevens


# -- het resultaat -------------------------------------------------------------------------------


def _velden_als_json(velden: BonVelden) -> dict[str, object]:
    """Alleen tekst en getallen als tekst: een bedrag als `Decimal` blijft zo exact in JSON."""
    return {
        "leverancier": velden.leverancier,
        "datum": velden.datum.isoformat() if velden.datum else None,
        "totaal": str(velden.totaal) if velden.totaal is not None else None,
        "factuurnummer": velden.factuurnummer,
        "btw": {str(tarief): str(bedrag) for tarief, bedrag in sorted(velden.btw.items())},
        "btw_nummer": velden.btw_nummer,
        "kvk_nummer": velden.kvk_nummer,
        "iban": velden.iban,
        "vervaldatum": velden.vervaldatum.isoformat() if velden.vervaldatum else None,
        "valuta": velden.valuta,
    }


def _log(tenant_id: object, sha256: str, start: float, uitkomst: dict[str, object]) -> None:
    geldig = isinstance(tenant_id, int) and not isinstance(tenant_id, bool)
    tenant = tenant_id if geldig else "ongeldig"
    duur_ms = int((time.perf_counter() - start) * 1000)
    status = str(uitkomst["status"])
    # Nooit tekst van de bon, een bestandsnaam of een uitzonderingsmelding in het log; bij een fout
    # alleen de NAAM van het type, zodat een operator ziet wat er misging.
    reden = f" reden={uitkomst['reden']}" if status == "fout" else ""
    logger.info(
        "bonlezer opdracht klaar: tenant=%s sha256=%s duur_ms=%d status=%s%s",
        tenant,
        sha256 or "-",
        duur_ms,
        status,
        reden,
    )


def _lees_via_privekopie(gegevens: bytes, suffix: str, lezer: _Lezer) -> str:
    with tempfile.TemporaryDirectory(prefix="bon-") as tijdelijk:
        kopie = Path(tijdelijk) / f"bon{suffix}"
        vlaggen = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(kopie, vlaggen, 0o600), "wb") as uit:
            uit.write(gegevens)
        return lezer.lees(kopie)


def verwerk_opdracht(
    root: Path, tenant_id: int, bestand_id: str, *, lezer: _Lezer
) -> dict[str, object]:
    """Lees het bestand van deze tenant en geef status, reden, sha256 en de velden terug.

    Een weigering of fout is een UITKOMST (`status` `geweigerd` of `fout`) en geen uitzondering:
    een herhaling van dezelfde opdracht geeft hetzelfde antwoord, dus Dramatiq hoeft niet te herhalen.
    """
    start = time.perf_counter()
    sha256 = ""
    try:
        tenant, bestand = _controleer_opdracht(tenant_id, bestand_id)
        gegevens = _lees_bytes(_open_bestand(root, tenant, bestand))
        sha256 = hashlib.sha256(gegevens).hexdigest()
        tekst = _lees_via_privekopie(gegevens, Path(bestand).suffix, lezer)
        uitkomst: dict[str, object] = {
            "status": "gelezen",
            "reden": "",
            "sha256": sha256,
            "velden": _velden_als_json(lees_velden(tekst)),
        }
    except (_Geweigerd, OngeldigBestand) as fout:
        # Geen sha256 bij een weigering: die zou "bestaat" van "bestaat niet" onderscheiden.
        uitkomst = {"status": "geweigerd", "reden": str(fout), "sha256": "", "velden": {}}
    except Exception as fout:  # onverwacht: alleen het type, want de melding kan bontekst bevatten
        uitkomst = {"status": "fout", "reden": type(fout).__name__, "sha256": sha256, "velden": {}}
    _log(tenant_id, sha256, start, uitkomst)
    return uitkomst


# -- de broker en de actor ------------------------------------------------------------------------

# BEWUST GEEN `dramatiq.set_broker()` en een actor die EXPLICIET aan deze broker bindt, zoals de
# leerworker (`src/core/learning/worker.py`): de importvolgorde bepaalt dan niet op welke broker een
# actor terechtkomt. De opdracht noemt de broker bij naam: `dramatiq src.core.als.bonlezer.worker:_broker`
# (bewaakt door tests/architecture/test_workers_bind_a_real_broker.py).
STANDAARD_BROKER_URL = "redis://bonlezer-redis:6379/0"


def broker_url() -> str:
    """De URL van de EIGEN Redis van de bonlezer (dag 3, besluit regie).

    Bewust een eigen variabele en GEEN terugval op `DRAMATIQ_BROKER_URL` of `REDIS_URL`: die wijzen in
    elk ander proces (ook de backend, die dit module voor de upload-route importeert) naar de hoofd-Redis,
    en een bonlezer die daar stilletjes op terechtkomt maakt de aparte Redis zinloos.
    """
    url = (os.getenv("BONLEZER_BROKER_URL") or STANDAARD_BROKER_URL).strip()
    seconden = _time_out_seconden()
    if seconden is None:
        return url
    scheiding = "&" if "?" in url else "?"
    return f"{url}{scheiding}socket_timeout={seconden}&socket_connect_timeout={seconden}"


def _time_out_seconden() -> int | None:
    """De time-out (hele seconden) uit `BONLEZER_SOCKET_TIMEOUT`, of `None` als die niet (bruikbaar) is gezet.

    De backend zet die (5 s): een worker die Redis pauzeert (`CLIENT PAUSE`) mag de threadpool van de
    backend dan niet onbepaald laten wachten. De worker zelf zet hem NIET: zijn consument wacht bewust
    lang op een volgende opdracht. De time-out gaat IN DE URL, niet als los argument: bij `url=` maakt
    dramatiq zelf een verbindingspool en redis-py negeert losse `socket_timeout`-argumenten dan (gemeten
    door de code-reviewer, dag 3 ronde 2). Een onbruikbare waarde (leeg, geen geheel getal, nul,
    negatief) geeft geen time-out.
    """
    try:
        seconden = int(os.getenv("BONLEZER_SOCKET_TIMEOUT", "").strip())
    except ValueError:
        return None
    return seconden if seconden > 0 else None


_broker_url = broker_url()
#: Een EIGEN sleutelvoorvoegsel voor de wachtrij en de resultaten. Sinds dag 3 heeft de bonlezer een EIGEN
#: Redis (compose: `bonlezer-redis`); het voorvoegsel beschermt dus niets tegen andere systemen maar houdt
#: de sleutels herkenbaar. De worker heeft daar volledige rechten: een gecompromitteerde parser kan alleen
#: de bonlezer-Redis verstoren, niet de hoofd-Redis.
NAAMRUIMTE = "bonlezer"
RESULTAAT_NAAMRUIMTE = "bonlezer-results"

#: De uitkomst blijft even lang in Redis staan als de bon zelf bij de klant (30 dagen, de belofte op het scherm).
#: Gemeten op de acceptatie (2026-10-17): met 300 s verdween het leesresultaat na ~6 minuten en moest de
#: medewerker alles zelf invullen. De backend legt het resultaat daarnaast bij de eerste keer ophalen vast naast
#: de bon (`upload.py`), want Redis bewaart niets op schijf.
RESULTAAT_TTL_MS = 30 * 24 * 60 * 60 * 1000
TIJDLIMIET_MS = 180_000

_broker = RedisBroker(url=_broker_url, namespace=NAAMRUIMTE)  # type: ignore[no-untyped-call]  # dramatiq mist stubs


class _VasteOpties(Middleware):
    """Zet de opties van elk bericht terug op vaste waarden.

    Een bericht draagt eigen `options` (`max_retries`, `time_limit`, `pipe_target`, `on_failure`, ...)
    die de instellingen van de actor kunnen overschrijven. Wie in de wachtrij kan schrijven, kon daarmee
    de tijdslimiet oprekken of een vervolgactor aanwijzen. De grenzen staan hier vast, ongeacht wat het
    bericht meebrengt (`redis_message_id` en de herhaaltellers blijven staan). `result_ttl` zetten we
    mee als gordel: in dramatiq 1.16 leest de Results-middleware die alleen uit de actor (gelezen in de
    bron door de code-reviewer, niet met een vijandig bericht gemeten).
    """

    def before_process_message(
        self, broker: dramatiq.Broker, message: dramatiq.Message[object]
    ) -> None:
        for sleutel in ("pipe_target", "pipe_ignore", "on_failure", "on_success"):
            message.options.pop(sleutel, None)
        message.options["max_retries"] = 0
        message.options["time_limit"] = TIJDLIMIET_MS
        message.options["result_ttl"] = RESULTAAT_TTL_MS


_broker.add_middleware(  # type: ignore[no-untyped-call]  # dramatiq mist stubs
    Results(  # type: ignore[no-untyped-call]
        backend=RedisBackend(url=_broker_url, namespace=RESULTAAT_NAAMRUIMTE)
    )
)
_broker.add_middleware(_VasteOpties(), before=TimeLimit)  # type: ignore[no-untyped-call]


def haal_resultaat(
    bericht: dramatiq.Message[dict[str, object]],
    *,
    wacht_ms: int = 0,
    broker: dramatiq.Broker | None = None,
) -> dict[str, object]:
    """Haal de uitkomst van een verstuurde opdracht op uit de resultaatopslag in Redis.

    `Message.get_result()` van dramatiq leest de GLOBALE broker, en deze actor bindt bewust aan een
    eigen broker (zie boven); daar zou het "the broker doesn't have a results backend" geven. De backend
    (dag 3) haalt het resultaat dus met deze functie op. Zonder wachttijd en zonder resultaat volgt
    `ResultMissing`; met een wachttijd en zonder resultaat `ResultTimeout` (beide uit `dramatiq.results`).
    """
    backend = (broker or _broker).get_results_backend()  # type: ignore[no-untyped-call]  # dramatiq mist stubs
    if backend is None:
        raise RuntimeError("de broker heeft geen resultaatopslag")
    resultaat = backend.get_result(bericht, block=wacht_ms > 0, timeout=max(wacht_ms, 1))
    return cast(dict[str, object], resultaat)


_lezer_instantie: BonLezer | None = None


def _lezer() -> BonLezer:
    global _lezer_instantie
    if _lezer_instantie is None:
        modellen = Path(os.environ.get("BONLEZER_ARTIFACTS", STANDAARD_MODELLEN))
        _lezer_instantie = BonLezer(artifacts_pad=modellen)
    return _lezer_instantie


class _LuiweLezer:
    """Maakt de zware lezer pas aan bij de eerste echte lezing: een geweigerde opdracht laadt geen modellen."""

    def lees(self, pad: Path) -> str:
        return _lezer().lees(pad)


# `max_retries=0`: een weigering of een kapot bestand is bij een herhaling hetzelfde; `time_limit` in
# milliseconden ligt boven de `document_timeout` van de lezer (120 s). Dezelfde waarden worden per
# bericht afgedwongen door `_VasteOpties`.
@dramatiq.actor(
    broker=_broker,
    queue_name=QUEUE,
    max_retries=0,
    time_limit=TIJDLIMIET_MS,
    store_results=True,
    result_ttl=RESULTAAT_TTL_MS,
)
def lees_bon(tenant_id: int, bestand_id: str) -> dict[str, object]:
    return verwerk_opdracht(upload_root(), tenant_id, bestand_id, lezer=_LuiweLezer())
