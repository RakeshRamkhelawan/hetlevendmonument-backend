"""Een bon krijgt de factuurvelden (iban, vervaldatum, valuta) nooit terug; een inkoopfactuur wel (crediteuren dag 2, Gate 2).

De veldenlaag zoekt een IBAN in de hele tekst. Op een kassabon kan dat een persoonsgegeven zijn; het hoort niet in het antwoord van de
bonnenpagina. Een inkoopfactuur (soort `factuur`) heeft de velden juist nodig voor de crediteurenagent.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.core.als.bonlezer.upload import BonDienst

_PDF = b"%PDF-1.4 een bon of factuur"
_VELDEN: dict[str, object] = {
    "leverancier": "Bakkerij",
    "datum": "2026-10-15",
    "totaal": "6.98",
    "iban": "NL91ABNA0417164300",
    "vervaldatum": "2026-10-31",
    "valuta": "EUR",
}


def _dienst(root: Path) -> BonDienst:
    verstuurd: dict[str, tuple[int, str]] = {}

    def verstuur(tenant_id: int, bestand_id: str) -> str:
        verstuurd[bestand_id] = (tenant_id, bestand_id)
        return bestand_id

    def haal(message_id: str) -> dict[str, object]:
        tenant_id, bestand_id = verstuurd[message_id]
        inhoud = (root / str(tenant_id) / bestand_id).read_bytes()
        return {
            "status": "gelezen",
            "reden": "",
            "sha256": hashlib.sha256(inhoud).hexdigest(),
            "velden": dict(_VELDEN),
        }

    return BonDienst(root, verstuur=verstuur, haal=haal)


def _velden(dienst: BonDienst, bestand_id: str) -> dict[str, object]:
    velden = dienst.status(1, bestand_id)["velden"]
    assert isinstance(velden, dict)
    return velden


def test_a_receipt_does_not_show_the_invoice_fields(tmp_path: Path) -> None:
    dienst = _dienst(tmp_path)
    bestand_id = dienst.uploaden(1, "bon.pdf", _PDF)

    velden = _velden(dienst, bestand_id)

    assert [k for k in ("iban", "vervaldatum", "valuta") if k in velden] == []


def test_a_receipt_keeps_its_own_fields(tmp_path: Path) -> None:
    dienst = _dienst(tmp_path)
    bestand_id = dienst.uploaden(1, "bon.pdf", _PDF)

    assert _velden(dienst, bestand_id)["totaal"] == "6.98"


def test_an_invoice_shows_the_invoice_fields(tmp_path: Path) -> None:
    dienst = _dienst(tmp_path)
    bestand_id = dienst.uploaden(1, "factuur.pdf", _PDF, "factuur")

    velden = _velden(dienst, bestand_id)

    assert (velden["iban"], velden["vervaldatum"], velden["valuta"]) == (
        "NL91ABNA0417164300",
        "2026-10-31",
        "EUR",
    )


def test_a_receipt_stays_without_the_invoice_fields_when_asked_again(tmp_path: Path) -> None:
    """Het tweede antwoord komt uit het vastgelegde resultaat naast de bon: ook daar horen de velden niet bij."""
    dienst = _dienst(tmp_path)
    bestand_id = dienst.uploaden(1, "bon.pdf", _PDF)
    _velden(dienst, bestand_id)

    velden = _velden(dienst, bestand_id)

    assert "iban" not in velden


def test_an_upload_without_a_kind_is_a_receipt(tmp_path: Path) -> None:
    dienst = _dienst(tmp_path)
    bestand_id = dienst.uploaden(1, "bon.pdf", _PDF)

    assert dienst.soort(1, bestand_id) == "bon"
