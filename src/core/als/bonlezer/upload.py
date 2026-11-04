"""De opslag- en statuskant van de bonlezer in de backend (bonlezer dag 3).

`BonDienst.uploaden` bewaart een bon onder `<uploadmap>/<tenant_id>/<bestand_id>` (dezelfde plek die de
worker alleen-lezen ziet), stuurt de opdracht `lees_bon` en geeft het `bestand_id` terug.
`BonDienst.status` toont de uitkomst, maar alleen als die bij DIT bestand hoort.

Waarom zo:

- **Controleren voor opslaan.** Grootte, extensie en de eerste bytes (de "magic bytes") worden getoetst op
  het bestand in het geheugen; pas daarna komt er iets op schijf. Een geweigerd bestand laat niets achter.
- **Het `bestand_id` is toeval.** `secrets.token_hex(16)` plus een extensie uit een vaste lijst: 128 bit
  die niemand kan raden, ook niet met schrijfrechten op de wachtrij (de worker vertrouwt de opdracht en
  weet niet wiens tenant het is). Nooit afgeleid van de inhoud, een teller of een naam van de gebruiker.
  De oorspronkelijke bestandsnaam staat WEL in het metabestand (alleen voor het scherm: zonder pad en stuurtekens,
  hooguit `MAX_NAAM` tekens); hij wordt nooit gebruikt om iets op te slaan en komt in geen log of auditregel.
- **Geen tabel.** Wat de backend per upload moet onthouden (sha256, bericht-id, tijdstip, afgerond) staat in
  `<bestand_id>.meta.json` naast de bon. Dat volume is voor de worker ALLEEN-LEZEN: hij kan de metadata niet
  aanpassen. Hij kan haar wel LEZEN (en de sha256 volgt uit de bon zelf).
- **Echtheid van het resultaat.** De worker meldt de sha256 van de bytes die hij las. Die moet gelijk zijn aan
  wat de backend bij de upload zelf uitrekende; anders (of zonder sha256) is de status `ongeldig` en komen er
  geen velden mee. Dat beschermt tegen VERMENGING en bugs (het resultaat van een ander bestand), NIET tegen een
  kwaadwillende worker: die ziet de metadata en kan een passend resultaat verzinnen. Daarom worden de velden
  ook aan een vast schema getoetst (`_toets_velden`), en moet een mens de velden bevestigen voordat er een
  btw-concept uit komt (eis voor dag 4).
- **Quotum.** Maximaal `MAX_OPENSTAAND` opdrachten per tenant die nog niet zijn afgerond en jonger zijn dan
  `OPENSTAAND_SECONDEN`. Een gelijktijdige upload kan het quotum met een of twee overschrijden (geen slot);
  het doel is bescherming van de wachtrij, geen exacte telling.

Het leesresultaat staat `RESULTAAT_TTL_MS` (30 dagen) in de Redis van de bonlezer en wordt bij de eerste keer
ophalen ook naast de bon vastgelegd (`<bestand_id>.resultaat.json`, geen tabel). De opruiming verwijdert dat
bestand samen met de bon na 30 dagen.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import unicodedata
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path

from dramatiq.results import ResultMissing

from src.core.als.bonlezer.lezer import MAX_BYTES
from src.core.als.bonlezer.worker import TIJDLIMIET_MS

logger = logging.getLogger(__name__)

#: Maximaal aantal opdrachten per tenant dat tegelijk openstaat (nog niet afgerond en niet verlopen).
MAX_OPENSTAAND = 5

#: Zo lang telt een opdracht als openstaand voor het quotum: ruim boven de bewaartijd van het resultaat,
#: zodat een opdracht die nooit klaar komt het quotum niet eeuwig bezet houdt.
OPENSTAAND_SECONDEN = 600

#: Zo lang kan een opdracht zonder resultaat nog wachten: de tijdslimiet van de worker plus een marge
#: (180 s + 300 s). Daarna volgt `verlopen`, nooit meer `wachten` (code-review ronde 1). Los van de bewaartijd
#: van het resultaat zelf (`RESULTAAT_TTL_MS`, 30 dagen): een opdracht die nooit klaar komt (worker weg, Redis
#: herstart) hoort niet 30 dagen "wachten" te blijven.
VERLOOP_SECONDEN = TIJDLIMIET_MS // 1000 + 300

MAX_REDEN = 200

#: Zo veel tekens van de oorspronkelijke bestandsnaam worden bewaard en getoond.
MAX_NAAM = 120

_TIFF = (b"II*\x00", b"MM\x00*")

#: extensie -> toegestane beginbytes. Alleen wat de lezer kent, zonder `bmp`.
_TYPES: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".tif": _TIFF,
    ".tiff": _TIFF,
}

_BESTAND_ID = re.compile(r"[0-9a-f]{32}\.(?:pdf|png|jpg|jpeg|tif|tiff)")
_EINDSTATUS = frozenset({"gelezen", "geweigerd", "fout"})

_NIET_BESCHIKBAAR = "De bonlezer is nu niet bereikbaar. Probeer het over een paar minuten opnieuw."
_NIET_OPGESLAGEN = (
    "Het bestand kon nu niet worden opgeslagen. Probeer het over een paar minuten opnieuw."
)

# De velden die de worker mag melden en hun vorm. Alles daarbuiten is `ongeldig`: ook met de juiste hash
# is de uitkomst van een worker niet te vertrouwen (hij leest de bon met een parser die vijandige invoer krijgt).
_VELDEN = frozenset(
    {
        "leverancier",
        "datum",
        "totaal",
        "factuurnummer",
        "btw",
        "btw_nummer",
        "kvk_nummer",
        "iban",
        "vervaldatum",
        "valuta",
    }
)
# De leverancier is bij de worker een hele tekstregel (tot 500 tekens) en een factuurnummer kan langer
# dan 40 zijn; de grenzen volgen wat `veldenlaag.py` kan leveren (code-review dag 3, ronde 2).
_MAX_LENGTE = {"leverancier": 500, "factuurnummer": 64}
_STANDAARD_LENGTE = 40
_MAX_BTW_TARIEVEN = 10
#: Alleen voor een inkoopfactuur: een bon toont ze niet (zie `BonDienst.status`).
_FACTUURVELDEN = frozenset({"iban", "vervaldatum", "valuta"})
_DECIMAAL = re.compile(r"-?[0-9]{1,12}(?:\.[0-9]{1,4})?")
_DATUM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_TARIEF = re.compile(r"[0-9]{1,3}")
_IBAN = re.compile(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}")
_VALUTA = re.compile(r"[A-Z]{3}")


class UploadFout(Exception):
    """Een upload of statusvraag die niet kan; `status_code` en `boodschap` zijn voor de gebruiker."""

    def __init__(self, status_code: int, error_code: str, boodschap: str) -> None:
        super().__init__(boodschap)
        self.status_code = status_code
        self.error_code = error_code
        self.boodschap = boodschap


class BonNietGevonden(Exception):
    """Het bestand bestaat niet voor deze tenant (ook als het van een andere tenant is)."""


Verstuur = Callable[[int, str], str]
Haal = Callable[[str], dict[str, object]]


class BonDienst:
    def __init__(
        self,
        root: Path,
        *,
        verstuur: Verstuur,
        haal: Haal,
        nu: Callable[[], datetime] | None = None,
    ) -> None:
        self._root = root
        self._verstuur = verstuur
        self._haal = haal
        self._nu = nu or (lambda: datetime.now(timezone.utc))

    @property
    def root(self) -> Path:
        """De uploadmap van deze dienst: wie naast een upload iets bewaart (`factuur.py`) gebruikt dezelfde map."""
        return self._root

    # -- uploaden -----------------------------------------------------------------------------------

    def uploaden(
        self, tenant_id: int, bestandsnaam: str, inhoud: bytes, soort: str = "bon"
    ) -> str:
        """Bewaar de bon van deze tenant, stuur de opdracht en geef het `bestand_id` terug.

        `soort` is `bon` (de bonnenpagina) of `factuur` (een inkoopfactuur voor de crediteurenagent). Het staat in het metabestand:
        een bon wordt nooit door de crediteurenagent opgepakt, ook niet als iemand zijn `bestand_id` kent.

        Volgorde (security-review ronde 1): eerst RESERVEREN (bon en metabestand zonder bericht-id),
        dan tellen, dan pas versturen. Staat de reservering er niet voor het tellen, dan ziet elke
        gelijktijdige upload nul openstaande opdrachten en is het quotum geen begrenzing.
        """
        extensie = self._toets_upload(tenant_id, bestandsnaam, inhoud)
        bestand_id = secrets.token_hex(16) + extensie
        try:
            self._reserveer(
                tenant_id, bestand_id, inhoud, schoon_bestandsnaam(bestandsnaam), soort
            )
            self._controleer_quotum(tenant_id)
            message_id = self._verstuur(tenant_id, bestand_id)
            self._leg_bericht_vast(tenant_id, bestand_id, message_id)
        except UploadFout as fout:
            self._ruim_op(tenant_id, bestand_id)
            logger.info("bonlezer upload geweigerd: tenant=%s code=%s", tenant_id, fout.error_code)
            raise
        except OSError as fout:
            self._ruim_op(tenant_id, bestand_id)
            logger.error(
                "bonlezer opslag mislukt: tenant=%s fouttype=%s", tenant_id, type(fout).__name__
            )
            raise UploadFout(503, "OPSLAG_NIET_BESCHIKBAAR", _NIET_OPGESLAGEN) from fout
        except Exception as fout:
            self._ruim_op(tenant_id, bestand_id)
            logger.error(
                "bonlezer upload mislukt: tenant=%s fouttype=%s", tenant_id, type(fout).__name__
            )
            raise UploadFout(503, "BONLEZER_NIET_BESCHIKBAAR", _NIET_BESCHIKBAAR) from fout
        logger.info(
            "bonlezer upload: tenant=%s bestand_id=%s bytes=%d", tenant_id, bestand_id, len(inhoud)
        )
        return bestand_id

    @staticmethod
    def _toets_upload(tenant_id: int, bestandsnaam: str, inhoud: bytes) -> str:
        try:
            _controleer_tenant(tenant_id)
            return _controleer_bestand(bestandsnaam, inhoud)
        except UploadFout as fout:
            # Alleen de code: geen bestandsnaam en geen inhoud in het log.
            logger.info("bonlezer upload geweigerd: tenant=%s code=%s", tenant_id, fout.error_code)
            raise

    def _reserveer(
        self, tenant_id: int, bestand_id: str, inhoud: bytes, naam: str, soort: str
    ) -> None:
        os.makedirs(self._root / str(tenant_id), mode=0o755, exist_ok=True)
        _schrijf_nieuw(self._root / str(tenant_id) / bestand_id, inhoud)
        self._schrijf_meta(
            tenant_id,
            bestand_id,
            {
                "sha256": hashlib.sha256(inhoud).hexdigest(),
                "naam": naam,
                "soort": soort,
                "message_id": "",
                "aangemaakt": self._nu().isoformat(),
                "afgerond": False,
            },
        )

    def _leg_bericht_vast(self, tenant_id: int, bestand_id: str, message_id: str) -> None:
        meta = _lees_json(self._meta_pad(tenant_id, bestand_id))
        if meta is None:
            raise OSError("het metabestand is verdwenen")
        meta["message_id"] = message_id
        self._schrijf_meta(tenant_id, bestand_id, meta)

    def _ruim_op(self, tenant_id: int, bestand_id: str) -> None:
        tenantmap = self._root / str(tenant_id)
        _verwijder(tenantmap / bestand_id)
        _verwijder(self._meta_pad(tenant_id, bestand_id))
        for rest in tenantmap.glob(f"{bestand_id}.meta.json.*.tmp"):
            _verwijder(rest)

    # -- status -------------------------------------------------------------------------------------

    def naam(self, tenant_id: int, bestand_id: str) -> str | None:
        """De naam die de gebruiker de upload gaf (zonder pad en stuurtekens), of `None`. Alleen voor het scherm en het ticket."""
        meta = self._lees_meta(tenant_id, bestand_id)
        waarde = meta.get("naam") if meta is not None else None
        return waarde if isinstance(waarde, str) and waarde else None

    def soort(self, tenant_id: int, bestand_id: str) -> str | None:
        """`bon` of `factuur`; `None` als het bestand niet van deze tenant is. Een upload van voor dit veld is een bon."""
        meta = self._lees_meta(tenant_id, bestand_id)
        if meta is None:
            return None
        waarde = meta.get("soort")
        return waarde if isinstance(waarde, str) else "bon"

    def status(self, tenant_id: int, bestand_id: str) -> dict[str, object]:
        """De stand van een upload van DEZE tenant; een ander of onbekend bestand is `BonNietGevonden`.

        De velden `iban`, `vervaldatum` en `valuta` horen bij een INKOOPFACTUUR (crediteurenagent). Een bon krijgt ze nooit terug:
        de veldenlaag zoekt een IBAN in de hele tekst en het IBAN op een kassabon kan een persoonsgegeven zijn (Gate 2).
        """
        antwoord = self._status_ruw(tenant_id, bestand_id)
        velden = antwoord.get("velden")
        if isinstance(velden, dict) and self.soort(tenant_id, bestand_id) != "factuur":
            antwoord = {
                **antwoord,
                "velden": {k: v for k, v in velden.items() if k not in _FACTUURVELDEN},
            }
        return antwoord

    def _status_ruw(self, tenant_id: int, bestand_id: str) -> dict[str, object]:
        meta = self._lees_meta(tenant_id, bestand_id)
        if meta is None:
            raise BonNietGevonden(bestand_id)
        vastgelegd = self._lees_resultaat(tenant_id, bestand_id)
        if vastgelegd is not None:
            return vastgelegd
        if not meta.get("message_id"):
            return {"bestand_id": bestand_id, "status": "wachten"}  # nog niet verstuurd
        try:
            resultaat = self._haal(str(meta["message_id"]))
        except ResultMissing:
            # Het resultaat leeft hooguit `VERLOOP_SECONDEN`; is de bon al afgerond, dan is het weg.
            verlopen = (
                bool(meta.get("afgerond")) or self._leeftijd_seconden(meta) > VERLOOP_SECONDEN
            )
            return {"bestand_id": bestand_id, "status": "verlopen" if verlopen else "wachten"}
        except Exception as fout:
            logger.error(
                "bonlezer status mislukt: tenant=%s fouttype=%s", tenant_id, type(fout).__name__
            )
            raise UploadFout(503, "BONLEZER_NIET_BESCHIKBAAR", _NIET_BESCHIKBAAR) from fout
        antwoord = self._toets_resultaat(tenant_id, bestand_id, meta, resultaat)
        if antwoord["status"] != "ongeldig":
            self._leg_resultaat_vast(tenant_id, bestand_id, antwoord)
        if not meta.get("afgerond"):
            meta["afgerond"] = True
            self._schrijf_meta(tenant_id, bestand_id, meta)
        return antwoord

    # -- intern -------------------------------------------------------------------------------------

    def _resultaat_pad(self, tenant_id: int, bestand_id: str) -> Path:
        return self._root / str(tenant_id) / f"{bestand_id}.resultaat.json"

    def _leg_resultaat_vast(
        self, tenant_id: int, bestand_id: str, antwoord: dict[str, object]
    ) -> None:
        """Bewaar het getoetste leesresultaat naast de bon; een bestaand GELDIG resultaat blijft staan."""
        doel = self._resultaat_pad(tenant_id, bestand_id)
        if lees_vastgelegd_resultaat(doel, bestand_id) is not None:
            return
        record = {sleutel: waarde for sleutel, waarde in antwoord.items() if sleutel != "bestand_id"}
        tijdelijk = doel.with_name(f"{doel.name}.{secrets.token_hex(4)}.tmp")
        try:
            _schrijf_nieuw(tijdelijk, json.dumps(record).encode("utf-8"))
            os.replace(tijdelijk, doel)
        except OSError as fout:
            # Het antwoord zelf is al goed; alleen het vastleggen mislukte. Volgende keer opnieuw.
            _verwijder(tijdelijk)
            logger.warning(
                "bonlezer resultaat vastleggen mislukt: tenant=%s fouttype=%s",
                tenant_id,
                type(fout).__name__,
            )

    def _lees_resultaat(self, tenant_id: int, bestand_id: str) -> dict[str, object] | None:
        """Het vastgelegde resultaat, opnieuw aan het schema getoetst; `None` als er geen is."""
        return lees_vastgelegd_resultaat(self._resultaat_pad(tenant_id, bestand_id), bestand_id)

    def _toets_resultaat(
        self, tenant_id: int, bestand_id: str, meta: dict[str, object], resultaat: object
    ) -> dict[str, object]:
        ongeldig: dict[str, object] = {
            "bestand_id": bestand_id,
            "status": "ongeldig",
            "reden": "het resultaat hoort niet bij dit bestand",
        }
        if not isinstance(resultaat, dict) or resultaat.get("status") not in _EINDSTATUS:
            logger.warning("bonlezer resultaat onbruikbaar: tenant=%s", tenant_id)
            return ongeldig
        status = str(resultaat["status"])
        if status == "gelezen":
            gemeld = resultaat.get("sha256")
            if not isinstance(gemeld, str) or not hmac.compare_digest(gemeld, str(meta["sha256"])):
                logger.warning("bonlezer resultaat met een andere hash: tenant=%s", tenant_id)
                return ongeldig
            velden = _toets_velden(resultaat.get("velden"))
            if velden is None:
                logger.warning(
                    "bonlezer resultaat met velden buiten het schema: tenant=%s", tenant_id
                )
                return ongeldig
            return {"bestand_id": bestand_id, "status": "gelezen", "reden": "", "velden": velden}
        reden = resultaat.get("reden")
        return {
            "bestand_id": bestand_id,
            "status": status,
            "reden": reden[:MAX_REDEN] if isinstance(reden, str) and _is_utf8(reden) else "",
        }

    def _openstaand(self, tenant_id: int) -> int:
        openstaand = 0
        for pad in (self._root / str(tenant_id)).glob("*.meta.json"):
            meta = _lees_json(pad)
            if (
                meta is not None
                and not meta.get("afgerond")
                and self._leeftijd_seconden(meta) <= OPENSTAAND_SECONDEN
            ):
                openstaand += 1
        return openstaand

    def _controleer_quotum(self, tenant_id: int) -> None:
        # De eigen reservering telt al mee: `>` en niet `>=`.
        if self._openstaand(tenant_id) > MAX_OPENSTAAND:
            raise UploadFout(
                429,
                "BONLEZER_QUOTUM",
                f"Er staan al {MAX_OPENSTAAND} bonnen te wachten om gelezen te worden. "
                "Probeer het over een paar minuten opnieuw.",
            )

    def _leeftijd_seconden(self, meta: dict[str, object]) -> float:
        aangemaakt = datetime.fromisoformat(str(meta["aangemaakt"]))
        return (self._nu() - aangemaakt).total_seconds()

    def _meta_pad(self, tenant_id: int, bestand_id: str) -> Path:
        return self._root / str(tenant_id) / f"{bestand_id}.meta.json"

    def _lees_meta(self, tenant_id: int, bestand_id: str) -> dict[str, object] | None:
        if (
            not isinstance(tenant_id, int)
            or isinstance(tenant_id, bool)
            or tenant_id <= 0
            or not isinstance(bestand_id, str)
            or not _BESTAND_ID.fullmatch(bestand_id)
        ):
            return None
        return _lees_json(self._meta_pad(tenant_id, bestand_id))

    def _schrijf_meta(self, tenant_id: int, bestand_id: str, meta: dict[str, object]) -> None:
        doel = self._meta_pad(tenant_id, bestand_id)
        tijdelijk = doel.with_name(f"{doel.name}.{secrets.token_hex(4)}.tmp")
        _schrijf_nieuw(tijdelijk, json.dumps(meta).encode("utf-8"))
        os.replace(tijdelijk, doel)


def _geldige_btw(waarde: object) -> bool:
    return (
        isinstance(waarde, dict)
        and len(waarde) <= _MAX_BTW_TARIEVEN
        and all(
            isinstance(tarief, str)
            and _TARIEF.fullmatch(tarief) is not None
            and isinstance(bedrag, str)
            and _DECIMAAL.fullmatch(bedrag) is not None
            for tarief, bedrag in waarde.items()
        )
    )


def _geldige_datum(waarde: str) -> bool:
    if _DATUM.fullmatch(waarde) is None:
        return False
    try:
        date.fromisoformat(waarde)
    except ValueError:
        return False
    return True


def _geldige_waarde(sleutel: str, waarde: object) -> bool:
    if waarde is None:
        return True
    if sleutel == "btw":
        return _geldige_btw(waarde)
    if not isinstance(waarde, str):
        return False
    if sleutel == "totaal":
        return _DECIMAAL.fullmatch(waarde) is not None
    if sleutel in ("datum", "vervaldatum"):
        return _geldige_datum(waarde)
    if sleutel == "iban":
        return _IBAN.fullmatch(waarde) is not None
    if sleutel == "valuta":
        return _VALUTA.fullmatch(waarde) is not None
    return len(waarde) <= _MAX_LENGTE.get(sleutel, _STANDAARD_LENGTE) and _is_utf8(waarde)


def _is_utf8(tekst: str) -> bool:
    """Een alleenstaande surrogaat is geen geldige tekst: JSON-antwoorden geven er een permanente 500 op."""
    try:
        tekst.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _toets_velden(velden: object) -> dict[str, object] | None:
    """De velden als ze binnen het vaste schema vallen, anders `None` (de uitkomst is dan `ongeldig`)."""
    if not isinstance(velden, dict) or not set(velden) <= _VELDEN:
        return None
    if not all(_geldige_waarde(str(sleutel), waarde) for sleutel, waarde in velden.items()):
        return None
    return dict(velden)


def _controleer_tenant(tenant_id: object) -> None:
    if not isinstance(tenant_id, int) or isinstance(tenant_id, bool) or tenant_id <= 0:
        raise UploadFout(422, "ONGELDIGE_TENANT", "Het verzoek is niet geldig.")


def _controleer_bestand(bestandsnaam: str, inhoud: bytes) -> str:
    """Geef de extensie terug als grootte, soort en beginbytes kloppen, anders `UploadFout`."""
    if len(inhoud) > MAX_BYTES:
        raise UploadFout(
            413,
            "FILE_TOO_LARGE",
            f"Het bestand is te groot (maximaal {MAX_BYTES // 1_000_000} MB).",
        )
    if not inhoud:
        raise UploadFout(422, "FILE_EMPTY", "Het bestand is leeg.")
    extensie = Path(str(bestandsnaam)).suffix.lower()
    toegestaan = _TYPES.get(extensie)
    if toegestaan is None:
        raise UploadFout(
            415, "FILE_TYPE_NOT_ALLOWED", "Alleen pdf, jpg, png en tif zijn toegestaan."
        )
    if not inhoud.startswith(toegestaan):
        raise UploadFout(415, "FILE_CONTENT_MISMATCH", "De inhoud past niet bij het soort bestand.")
    return extensie


def is_bestand_id(waarde: object) -> bool:
    """Is dit een bestandsnummer zoals `BonDienst.uploaden` ze maakt (32 hex-tekens en een bekende extensie)?"""
    return isinstance(waarde, str) and _BESTAND_ID.fullmatch(waarde) is not None


def schoon_bestandsnaam(naam: str) -> str:
    """De oorspronkelijke bestandsnaam voor het scherm: zonder pad, zonder stuurtekens, hooguit 120 tekens.

    De naam komt van de gebruiker en wordt alleen als TEKST getoond (nooit als pad of HTML gebruikt).
    """
    basis = re.split(r"[\\/]", str(naam))[-1]
    schoon = "".join(teken for teken in basis if unicodedata.category(teken) not in ("Cc", "Cf"))
    return schoon.encode("utf-8", "ignore").decode("utf-8").strip()[:MAX_NAAM]


def lees_vastgelegd_resultaat(pad: Path, bestand_id: str) -> dict[str, object] | None:
    """Het vastgelegde leesresultaat (`<id>.resultaat.json`), aan het schema getoetst.

    `None` als er geen is, en ook als het bestand kapot of onbekend is: de aanroeper valt dan terug op Redis en
    legt het opnieuw vast (security-review dag 4: een kapot bestand mocht de bon niet 30 dagen onleesbaar maken).
    """
    if not pad.exists():
        return None
    record = _lees_json(pad)
    if record is None:
        return None
    status = record.get("status")
    if status == "gelezen":
        velden = _toets_velden(record.get("velden"))
        if velden is None:
            logger.warning("bonlezer vastgelegd resultaat buiten het schema")
            return {
                "bestand_id": bestand_id,
                "status": "ongeldig",
                "reden": "het resultaat hoort niet bij dit bestand",
            }
        return {"bestand_id": bestand_id, "status": "gelezen", "reden": "", "velden": velden}
    if status in _EINDSTATUS:
        reden = record.get("reden")
        return {
            "bestand_id": bestand_id,
            "status": str(status),
            "reden": reden[:MAX_REDEN] if isinstance(reden, str) and _is_utf8(reden) else "",
        }
    return None


def _schrijf_nieuw(pad: Path, inhoud: bytes) -> None:
    vlaggen = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(pad, vlaggen, 0o644), "wb") as uit:
        uit.write(inhoud)


def _verwijder(pad: Path) -> None:
    try:
        pad.unlink()
    except OSError:
        logger.warning("bonlezer upload: opruimen mislukt")


def _lees_json(pad: Path) -> dict[str, object] | None:
    try:
        gelezen = json.loads(pad.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        # Diep geneste JSON (een beschadigd of vervalst bestand) is geen resultaat en geen 500.
        return None
    return gelezen if isinstance(gelezen, dict) else None
