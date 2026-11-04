"""Het SEPA-overschrijvingsbestand (pain.001.001.09) voor de crediteurenagent (crediteuren dag 3, Keten F).

Deze tests meten de STRUCTUUR met de standaardbibliotheek: namespace, aantallen, controlesom, bedragen, tekenset. De toets
tegen het XSD staat apart (`tests/integration/test_pain001_valideert_tegen_xsd.py`).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

import pytest

from src.core.exceptions import ValidatieFout
from src.core.services.sepa_betaalbestand import (
    NAMESPACE,
    BetaalRegel,
    Betaalopdracht,
    maak_pain001,
)

NS = {"p": NAMESPACE}
DEBITEUR_IBAN = "NL91ABNA0417164300"
LEVERANCIER_IBAN = "NL02ABNA0123456789"


# Vaste "vandaag" bij de vaste uitvoerdatum hieronder: de uitkomst hangt zo niet van de kalender af.
VANDAAG = date(2026, 10, 25)


def _regel(**over: object) -> BetaalRegel:
    basis: dict[str, object] = {
        "payable_id": 7,
        "naam": "Drukkerij Van Dijk BV",
        "iban": LEVERANCIER_IBAN,
        "bedrag_cents": 121000,
        "factuurnummer": "INK-2026-0042",
    }
    basis.update(over)
    return BetaalRegel(**basis)  # type: ignore[arg-type]


def _opdracht(regels: list[BetaalRegel] | None = None, **over: object) -> Betaalopdracht:
    basis: dict[str, object] = {
        "bericht_id": "hitl_0123456789abcdef",
        "gemaakt_op": datetime(2026, 10, 25, 12, 30, 15, 123456, tzinfo=timezone.utc),
        "uitvoerdatum": date(2026, 10, 27),
        "debiteur_naam": "Mijn Bedrijf BV",
        "debiteur_iban": DEBITEUR_IBAN,
        "regels": regels if regels is not None else [_regel()],
    }
    basis.update(over)
    return Betaalopdracht(**basis)  # type: ignore[arg-type]


def _lees(opdracht: Betaalopdracht) -> ET.Element:
    return ET.fromstring(maak_pain001(opdracht, vandaag=VANDAAG))


class TestDeKop:
    def test_the_document_uses_the_pain_001_001_09_namespace(self) -> None:
        assert _lees(_opdracht()).tag == f"{{{NAMESPACE}}}Document"

    def test_the_namespace_is_the_iso_20022_one_for_version_09(self) -> None:
        assert NAMESPACE == "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"

    def test_the_message_id_is_the_given_id(self) -> None:
        assert (
            _lees(_opdracht()).findtext(".//p:GrpHdr/p:MsgId", namespaces=NS)
            == "hitl_0123456789abcdef"
        )

    def test_the_creation_time_is_utc_without_microseconds(self) -> None:
        assert (
            _lees(_opdracht()).findtext(".//p:GrpHdr/p:CreDtTm", namespaces=NS)
            == "2026-10-25T12:30:15"
        )

    def test_the_header_counts_the_transactions(self) -> None:
        regels = [_regel(payable_id=1), _regel(payable_id=2, factuurnummer="B")]
        assert _lees(_opdracht(regels)).findtext(".//p:GrpHdr/p:NbOfTxs", namespaces=NS) == "2"

    def test_the_header_control_sum_is_the_sum_of_the_amounts(self) -> None:
        regels = [
            _regel(payable_id=1, bedrag_cents=121000),
            _regel(payable_id=2, bedrag_cents=5, factuurnummer="B"),
        ]
        assert (
            _lees(_opdracht(regels)).findtext(".//p:GrpHdr/p:CtrlSum", namespaces=NS) == "1210.05"
        )

    def test_the_initiating_party_is_the_debtor_name(self) -> None:
        assert (
            _lees(_opdracht()).findtext(".//p:GrpHdr/p:InitgPty/p:Nm", namespaces=NS)
            == "Mijn Bedrijf BV"
        )


class TestDeBetaalgroep:
    def test_the_payment_method_is_a_credit_transfer(self) -> None:
        assert _lees(_opdracht()).findtext(".//p:PmtInf/p:PmtMtd", namespaces=NS) == "TRF"

    def test_the_service_level_is_sepa(self) -> None:
        assert (
            _lees(_opdracht()).findtext(".//p:PmtInf/p:PmtTpInf/p:SvcLvl/p:Cd", namespaces=NS)
            == "SEPA"
        )

    def test_the_execution_date_is_the_given_date(self) -> None:
        assert (
            _lees(_opdracht()).findtext(".//p:PmtInf/p:ReqdExctnDt/p:Dt", namespaces=NS)
            == "2026-10-27"
        )

    def test_the_debtor_account_is_the_given_iban(self) -> None:
        assert (
            _lees(_opdracht()).findtext(".//p:PmtInf/p:DbtrAcct/p:Id/p:IBAN", namespaces=NS)
            == DEBITEUR_IBAN
        )

    def test_the_debtor_agent_says_the_bic_is_not_provided(self) -> None:
        assert (
            _lees(_opdracht()).findtext(
                ".//p:PmtInf/p:DbtrAgt/p:FinInstnId/p:Othr/p:Id", namespaces=NS
            )
            == "NOTPROVIDED"
        )

    def test_the_charges_are_shared(self) -> None:
        assert _lees(_opdracht()).findtext(".//p:PmtInf/p:ChrgBr", namespaces=NS) == "SLEV"

    def test_the_group_control_sum_equals_the_sum_of_the_amounts(self) -> None:
        wortel = _lees(
            _opdracht(
                [_regel(bedrag_cents=999), _regel(payable_id=8, bedrag_cents=1, factuurnummer="B")]
            )
        )
        assert wortel.findtext(".//p:PmtInf/p:CtrlSum", namespaces=NS) == "10.00"

    def test_there_is_no_postal_address_anywhere(self) -> None:
        # Vanaf 15 november 2026 staat een ongestructureerd adres niet meer toe in EPC-berichten; het bestand heeft er geen.
        assert _lees(_opdracht()).findall(".//p:PstlAdr", namespaces=NS) == []


class TestDeTransacties:
    def test_every_line_becomes_one_transaction(self) -> None:
        regels = [
            _regel(payable_id=1),
            _regel(payable_id=2, factuurnummer="B"),
            _regel(payable_id=3, factuurnummer="C"),
        ]
        assert len(_lees(_opdracht(regels)).findall(".//p:CdtTrfTxInf", namespaces=NS)) == 3

    def test_the_amount_has_two_decimals_and_the_euro_currency(self) -> None:
        bedrag = _lees(_opdracht([_regel(bedrag_cents=100)])).find(
            ".//p:CdtTrfTxInf/p:Amt/p:InstdAmt", namespaces=NS
        )
        assert (bedrag.text, bedrag.get("Ccy")) == ("1.00", "EUR")  # type: ignore[union-attr]

    def test_a_large_amount_keeps_every_cent(self) -> None:
        wortel = _lees(_opdracht([_regel(bedrag_cents=123456789012)]))
        assert (
            wortel.findtext(".//p:CdtTrfTxInf/p:Amt/p:InstdAmt", namespaces=NS) == "1234567890.12"
        )

    def test_the_creditor_account_is_the_supplier_iban(self) -> None:
        assert (
            _lees(_opdracht()).findtext(".//p:CdtTrfTxInf/p:CdtrAcct/p:Id/p:IBAN", namespaces=NS)
            == LEVERANCIER_IBAN
        )

    def test_the_creditor_name_is_the_supplier_name(self) -> None:
        assert (
            _lees(_opdracht()).findtext(".//p:CdtTrfTxInf/p:Cdtr/p:Nm", namespaces=NS)
            == "Drukkerij Van Dijk BV"
        )

    def test_the_remittance_names_the_invoice_number(self) -> None:
        assert (
            _lees(_opdracht()).findtext(".//p:CdtTrfTxInf/p:RmtInf/p:Ustrd", namespaces=NS)
            == "Factuur INK-2026-0042"
        )

    def test_the_end_to_end_id_is_unique_per_invoice(self) -> None:
        regels = [_regel(payable_id=1), _regel(payable_id=2, factuurnummer="B")]
        ids = [
            e.text
            for e in _lees(_opdracht(regels)).findall(
                ".//p:CdtTrfTxInf/p:PmtId/p:EndToEndId", namespaces=NS
            )
        ]
        assert ids == ["CRD-1", "CRD-2"]

    def test_the_xml_is_declared_utf8(self) -> None:
        assert maak_pain001(_opdracht(), vandaag=VANDAAG).startswith(
            b"<?xml version='1.0' encoding='UTF-8'?>"
        )


class TestDeTekenset:
    def test_an_ampersand_in_a_name_never_reaches_the_file_raw(self) -> None:
        assert b"&amp;" not in maak_pain001(
            _opdracht([_regel(naam="Smit & Zonen")]), vandaag=VANDAAG
        )

    def test_accents_are_transliterated(self) -> None:
        wortel = _lees(_opdracht([_regel(naam="Café Zürich")]))
        assert wortel.findtext(".//p:CdtTrfTxInf/p:Cdtr/p:Nm", namespaces=NS) == "Cafe Zurich"

    def test_a_name_is_cut_at_70_characters(self) -> None:
        wortel = _lees(_opdracht([_regel(naam="A" * 90)]))
        assert len(wortel.findtext(".//p:CdtTrfTxInf/p:Cdtr/p:Nm", namespaces=NS) or "") == 70

    def test_remittance_is_cut_at_140_characters(self) -> None:
        wortel = _lees(_opdracht([_regel(factuurnummer="N" * 200)]))
        assert len(wortel.findtext(".//p:CdtTrfTxInf/p:RmtInf/p:Ustrd", namespaces=NS) or "") == 140

    def test_a_name_that_is_empty_after_cleaning_is_refused(self) -> None:
        with pytest.raises(ValidatieFout):
            maak_pain001(_opdracht([_regel(naam="☃☃")]), vandaag=VANDAAG)

    def test_a_name_may_not_start_with_a_slash(self) -> None:
        wortel = _lees(_opdracht([_regel(naam="/Acme//BV/")]))
        assert wortel.findtext(".//p:CdtTrfTxInf/p:Cdtr/p:Nm", namespaces=NS) == "Acme BV"


class TestWatWordtGeweigerd:
    def test_an_empty_run_is_refused(self) -> None:
        with pytest.raises(ValidatieFout):
            maak_pain001(_opdracht([]), vandaag=VANDAAG)

    def test_a_wrong_checksum_creditor_iban_is_refused(self) -> None:
        with pytest.raises(ValidatieFout):
            maak_pain001(_opdracht([_regel(iban="NL02ABNA0123456780")]), vandaag=VANDAAG)

    def test_a_wrong_checksum_debtor_iban_is_refused(self) -> None:
        with pytest.raises(ValidatieFout):
            maak_pain001(_opdracht(debiteur_iban="NL91ABNA0417164301"), vandaag=VANDAAG)

    def test_a_non_sepa_iban_is_refused(self) -> None:
        with pytest.raises(ValidatieFout):
            maak_pain001(_opdracht([_regel(iban="US64SVBKUS6S3300958879")]), vandaag=VANDAAG)

    def test_a_zero_amount_is_refused(self) -> None:
        with pytest.raises(ValidatieFout):
            maak_pain001(_opdracht([_regel(bedrag_cents=0)]), vandaag=VANDAAG)

    def test_a_float_amount_is_refused(self) -> None:
        with pytest.raises(TypeError):
            maak_pain001(_opdracht([_regel(bedrag_cents=12.5)]), vandaag=VANDAAG)

    def test_the_same_invoice_twice_in_one_file_is_refused(self) -> None:
        with pytest.raises(ValidatieFout):
            maak_pain001(_opdracht([_regel(), _regel()]), vandaag=VANDAAG)

    def test_an_execution_date_in_the_past_is_refused(self) -> None:
        with pytest.raises(ValidatieFout):
            maak_pain001(_opdracht(uitvoerdatum=date(2026, 10, 24)), vandaag=date(2026, 10, 25))

    def test_a_message_id_longer_than_35_characters_is_refused(self) -> None:
        with pytest.raises(ValidatieFout):
            maak_pain001(_opdracht(bericht_id="x" * 36), vandaag=VANDAAG)

    def test_a_naive_creation_time_is_refused(self) -> None:
        with pytest.raises(ValidatieFout):
            maak_pain001(_opdracht(gemaakt_op=datetime(2026, 10, 25, 12, 0, 0)), vandaag=VANDAAG)


class TestLettersZonderOntbinding:
    """Letters die NFKD niet ontbindt mogen niet stilletjes verdwijnen (Gate 2, code 6)."""

    @pytest.mark.parametrize(
        ("invoer", "verwacht"),
        [
            ("Bjørn BV", "Bjorn BV"),
            ("Łukasz Kowalski", "Lukasz Kowalski"),
            ("Straße Bouw", "Strasse Bouw"),
            ("Æble Træ", "AEble Trae"),
        ],
    )
    def test_the_letter_is_replaced_not_dropped(self, invoer: str, verwacht: str) -> None:
        from src.core.services.sepa_betaalbestand import maak_tekst

        assert maak_tekst(invoer, 70) == verwacht
