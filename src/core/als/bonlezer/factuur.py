"""Welke upload is al een inkoopfactuur geworden? (crediteuren dag 2)

Een geuploade factuur wordt na de controle door een mens EEN keer een inkoopfactuur. Dit bestand onthoudt dat naast de upload,
zoals `BonBevestiging` dat voor een bon doet: `<bestand_id>.factuur.json` in de map van de tenant, geen tabel en geen migratie. De
opruiming (`opruimen.py`) verwijdert het samen met de bon na 30 dagen; de vastgelegde inkoopfactuur zelf blijft in de database.

Waarom een eigen bestand en niet alleen de unieke sleutel (leverancier, factuurnummer) van dag 1: die vangt een tweede UPLOAD van
dezelfde factuur, maar niet twee keer bevestigen van DEZELFDE upload met een gecorrigeerd nummer ertussen. Dat laatste zou een
dubbele betaling zijn.

`claim` maakt het bestand met `O_EXCL`: van twee gelijktijdige bevestigingen slaagt er precies een. Mislukt het vastleggen daarna,
dan geeft de aanroeper de claim vrij en kan de medewerker corrigeren en opnieuw bevestigen. Een proces dat tussen claim en
vrijgeven wegvalt laat de claim staan: die upload is dan op slot tot de opruiming; de medewerker uploadt de factuur opnieuw.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from src.core.als.bonlezer.upload import is_bestand_id

logger = logging.getLogger(__name__)


class FactuurKoppeling:
    def __init__(self, root: Path) -> None:
        self._root = root

    def lees(self, tenant_id: int, bestand_id: str) -> dict[str, object] | None:
        """De vastgelegde stand van deze upload, of `None` als er geen claim is of het bestand onleesbaar is."""
        try:
            record = json.loads(self._pad(tenant_id, bestand_id).read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            return None
        return record if isinstance(record, dict) else None

    def schrijf(self, tenant_id: int, bestand_id: str, record: dict[str, object]) -> None:
        """Vervang de stand van een GECLAIMDE upload (de agent noteert hier een ticket, een dubbele of een mislukking)."""
        pad = self._pad(tenant_id, bestand_id)
        tijdelijk = pad.with_name(f"{pad.name}.{secrets.token_hex(4)}.tmp")
        try:
            tijdelijk.write_bytes(json.dumps(record).encode("utf-8"))
            os.replace(tijdelijk, pad)
        except OSError as fout:
            logger.warning("factuurkoppeling schrijven mislukt: fouttype=%s", type(fout).__name__)
            try:
                tijdelijk.unlink()
            except OSError:
                pass

    def claim(self, tenant_id: int, bestand_id: str, door: int | None = None) -> bool:
        """Leg beslag op deze upload. `False` als er al een claim is (de upload is al vastgelegd of wordt dat nu).

        `door` is de gebruiker die de verwerking verantwoordt (de uploader); hij komt in de auditregel en als `created_by` van de
        factuur. De tijdstempel laat een claim die te lang `bezig` staat (de API viel weg tussen claim en uitkomst) overnemen.
        """
        pad = self._pad(tenant_id, bestand_id)
        vlaggen = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        try:
            beschrijver = os.open(pad, vlaggen, 0o644)
        except FileExistsError:
            return False
        with os.fdopen(beschrijver, "wb") as uit:
            uit.write(
                json.dumps(
                    {
                        "payable_id": None,
                        "uitkomst": "bezig",
                        "door": door,
                        "aangemaakt": datetime.now(timezone.utc).isoformat(),
                    }
                ).encode("utf-8")
            )
        return True

    def is_verlopen(self, stand: dict[str, object], minuten: int) -> bool:
        """Staat deze claim langer dan `minuten` op `bezig` zonder uitkomst? Dan is de verwerking onderbroken."""
        if stand.get("uitkomst") != "bezig" or stand.get("payable_id") is not None:
            return False
        aangemaakt = stand.get("aangemaakt")
        if not isinstance(aangemaakt, str):
            return True
        try:
            sinds = datetime.fromisoformat(aangemaakt)
        except ValueError:
            return True
        return (datetime.now(timezone.utc) - sinds).total_seconds() > minuten * 60

    def leg_vast(self, tenant_id: int, bestand_id: str, payable_id: int, *, door: int | None) -> None:
        """Noteer welke inkoopfactuur uit deze upload is ontstaan en wie hem bevestigde."""
        pad = self._pad(tenant_id, bestand_id)
        record = {
            "payable_id": payable_id,
            "door": door,
            "vastgelegd_op": datetime.now(timezone.utc).isoformat(),
        }
        tijdelijk = pad.with_name(f"{pad.name}.{secrets.token_hex(4)}.tmp")
        try:
            tijdelijk.write_bytes(json.dumps(record).encode("utf-8"))
            os.replace(tijdelijk, pad)
        except OSError as fout:
            # De factuur is WEL vastgelegd en de claim blijft staan: de upload kan dus niet nog een keer. Alleen het
            # nummer in het bestand ontbreekt; dat is voor het scherm een gemis, geen risico.
            logger.warning("factuurkoppeling vastleggen mislukt: fouttype=%s", type(fout).__name__)
            try:
                tijdelijk.unlink()
            except OSError:
                pass

    def geef_vrij(self, tenant_id: int, bestand_id: str) -> None:
        try:
            self._pad(tenant_id, bestand_id).unlink()
        except OSError as fout:
            logger.warning("factuurkoppeling vrijgeven mislukt: fouttype=%s", type(fout).__name__)

    def markeer_eerder_verlopen(self, tenant_id: int, bestand_id: str) -> None:
        """Onthoud naast de claim dat het ticket van deze upload niet op tijd is beoordeeld (crediteuren nazorg, punt 3).

        Een eigen bestandje, want `geef_vrij` verwijdert de claim zelf. Het volgende ticket van deze upload krijgt dan de zin "eerder
        voorgelegd, niet op tijd beoordeeld". Mislukt het schrijven, dan ontbreekt alleen die zin: de upload is wel vrijgegeven.
        """
        try:
            self._markering(tenant_id, bestand_id).write_text("verlopen", encoding="utf-8")
        except OSError as fout:
            logger.warning("factuurkoppeling markeren mislukt: fouttype=%s", type(fout).__name__)

    def was_eerder_verlopen(self, tenant_id: int, bestand_id: str) -> bool:
        try:
            return self._markering(tenant_id, bestand_id).is_file()
        except OSError:
            return False

    def _markering(self, tenant_id: int, bestand_id: str) -> Path:
        return self._pad(tenant_id, bestand_id).with_suffix(".verlopen")

    def payable_id(self, tenant_id: int, bestand_id: str) -> int | None:
        """De inkoopfactuur die uit deze upload is ontstaan, of `None` (nog niet, of de claim is nog niet afgerond)."""
        try:
            record = json.loads(self._pad(tenant_id, bestand_id).read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            return None
        waarde = record.get("payable_id") if isinstance(record, dict) else None
        return waarde if isinstance(waarde, int) and not isinstance(waarde, bool) else None

    def _pad(self, tenant_id: int, bestand_id: str) -> Path:
        if not isinstance(tenant_id, int) or isinstance(tenant_id, bool) or tenant_id <= 0:
            raise ValueError("ongeldige tenant")
        if not is_bestand_id(bestand_id):
            raise ValueError("ongeldig bestandsnummer")
        return self._root / str(tenant_id) / f"{bestand_id}.factuur.json"
