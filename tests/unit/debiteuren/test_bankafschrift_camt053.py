"""Een bankafschrift (CAMT.053) inlezen: de parser -- debiteuren vanzelf afronden, B2 (2026-10-20).

Besluit Rakesh 2026-10-20: "als het mogelijk is en niet al te veel werk Ja nu". Een CAMT.053-bestand (ISO 20022, de
standaard van de Nederlandse banken) wordt gelezen met de standaardbibliotheek achter een harde voorcontrole, en alleen
BIJSCHRIJVINGEN tellen. Dit bestand meet de parser `lees_camt053`; de kwaadaardige XML staat in
`test_bankafschrift_kwaadaardige_xml.py` en de koppelregel in `test_bankafschrift_koppelen.py`.

1. Het verzonnen voorbeeld (`tests/fixtures/bankafschrift/camt053_voorbeeld.xml`): zeven bijschrijvingen en een
   afschrijving die wordt overgeslagen; datum, bedrag (Decimal), valuta en omschrijving (vrije tekst EN
   betalingskenmerk) kloppen. Namespace-onafhankelijk (camt.053.001.02, .08 en zonder).
2. Geen debet, geen terugboeking (`RvslInd`), geen niet-geboekte regel (`Sts` anders dan BOOK).
3. Een bedrag dat niet te lezen is, geeft een foutmelding voor het HELE bestand (nooit stil overslaan), zonder de
   waarde te herhalen.
4. Grenzen: bestand boven 5 MB, boven 5000 regels, dieper dan 20 niveaus: geweigerd, in gewone taal.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.core.services.bankafschrift import (
    MAX_BYTES,
    MAX_TRANSACTIES,
    BankafschriftFout,
    lees_camt053,
)

VOORBEELD = (
    Path(__file__).resolve().parents[2] / "fixtures" / "bankafschrift" / "camt053_voorbeeld.xml"
)
KOP = '<?xml version="1.0" encoding="UTF-8"?>'


def _afschrift(
    entries: str, namespace: str = "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"
) -> bytes:
    ns = f' xmlns="{namespace}"' if namespace else ""
    return (
        f"{KOP}<Document{ns}><BkToCstmrStmt><Stmt><Id>S1</Id>{entries}</Stmt></BkToCstmrStmt></Document>"
    ).encode("utf-8")


def _entry(
    bedrag: str = "10.00",
    omschrijving: str = "F-1",
    *,
    richting: str = "CRDT",
    dag: str = "2026-10-05",
    extra: str = "",
    status: str = "BOOK",
) -> str:
    return (
        f'<Ntry><Amt Ccy="EUR">{bedrag}</Amt><CdtDbtInd>{richting}</CdtDbtInd>{extra}'
        f"<Sts>{status}</Sts><BookgDt><Dt>{dag}</Dt></BookgDt>"
        f"<NtryDtls><TxDtls><RmtInf><Ustrd>{omschrijving}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"
    )


class TestHetVoorbeeld:
    def _lezing(self):  # noqa: ANN202
        return lees_camt053(VOORBEELD.read_bytes())

    def test_seven_credits_are_read(self) -> None:
        assert len(self._lezing().bijschrijvingen) == 7

    def test_the_debit_is_skipped_and_counted(self) -> None:
        assert self._lezing().overgeslagen == 1

    def test_the_first_credit_has_date_amount_currency_and_text(self) -> None:
        eerste = self._lezing().bijschrijvingen[0]
        assert (eerste.datum, eerste.bedrag, eerste.valuta) == (
            date(2026, 10, 5),
            Decimal("121.00"),
            "EUR",
        )
        assert "F-2026-001" in eerste.omschrijving

    def test_the_amount_is_a_decimal(self) -> None:
        assert all(isinstance(b.bedrag, Decimal) for b in self._lezing().bijschrijvingen)

    def test_a_structured_reference_is_part_of_the_text(self) -> None:
        # Het debet (regel 5) wordt overgeslagen, dus regel 7 is de zesde bijschrijving (index 5).
        gestructureerd = self._lezing().bijschrijvingen[5]
        assert "F-2026-006" in gestructureerd.omschrijving

    def test_the_text_has_no_names_of_the_parties(self) -> None:
        tekst = " ".join(b.omschrijving for b in self._lezing().bijschrijvingen)
        assert "Voorbeeld Debiteur" not in tekst and "NL00VOOR" not in tekst


class TestDeParser:
    @pytest.mark.parametrize(
        "namespace",
        [
            "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02",
            "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08",
            "",
        ],
    )
    def test_the_namespace_does_not_matter(self, namespace: str) -> None:
        lezing = lees_camt053(_afschrift(_entry("5.00", "F-1"), namespace))
        assert [b.bedrag for b in lezing.bijschrijvingen] == [Decimal("5.00")]

    def test_a_debit_is_skipped(self) -> None:
        lezing = lees_camt053(_afschrift(_entry(richting="DBIT")))
        assert (lezing.bijschrijvingen, lezing.overgeslagen) == ([], 1)

    def test_a_reversal_is_skipped(self) -> None:
        lezing = lees_camt053(_afschrift(_entry(extra="<RvslInd>true</RvslInd>")))
        assert (lezing.bijschrijvingen, lezing.overgeslagen) == ([], 1)

    def test_a_pending_entry_is_skipped(self) -> None:
        lezing = lees_camt053(_afschrift(_entry(status="PDNG")))
        assert (lezing.bijschrijvingen, lezing.overgeslagen) == ([], 1)

    def test_an_entry_without_a_status_is_read(self) -> None:
        entry = _entry().replace("<Sts>BOOK</Sts>", "")
        assert len(lees_camt053(_afschrift(entry)).bijschrijvingen) == 1

    def test_the_value_date_is_used_when_there_is_no_booking_date(self) -> None:
        entry = _entry().replace(
            "<BookgDt><Dt>2026-10-05</Dt></BookgDt>", "<ValDt><Dt>2026-10-07</Dt></ValDt>"
        )
        assert lees_camt053(_afschrift(entry)).bijschrijvingen[0].datum == date(2026, 10, 7)

    def test_a_missing_date_is_none(self) -> None:
        entry = _entry().replace("<BookgDt><Dt>2026-10-05</Dt></BookgDt>", "")
        assert lees_camt053(_afschrift(entry)).bijschrijvingen[0].datum is None

    def test_a_date_time_is_cut_to_the_date(self) -> None:
        entry = _entry().replace(
            "<BookgDt><Dt>2026-10-05</Dt></BookgDt>",
            "<BookgDt><DtTm>2026-10-06T09:15:00</DtTm></BookgDt>",
        )
        assert lees_camt053(_afschrift(entry)).bijschrijvingen[0].datum == date(2026, 10, 6)

    def test_an_unreadable_date_is_none_and_not_an_error(self) -> None:
        entry = _entry(dag="gisteren")
        assert lees_camt053(_afschrift(entry)).bijschrijvingen[0].datum is None

    def test_several_transactions_in_one_entry_each_with_an_amount_are_separate(self) -> None:
        entry = (
            '<Ntry><Amt Ccy="EUR">30.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts>BOOK</Sts>'
            "<BookgDt><Dt>2026-10-05</Dt></BookgDt><NtryDtls>"
            '<TxDtls><AmtDtls><TxAmt><Amt Ccy="EUR">10.00</Amt></TxAmt></AmtDtls>'
            "<RmtInf><Ustrd>F-1</Ustrd></RmtInf></TxDtls>"
            '<TxDtls><AmtDtls><TxAmt><Amt Ccy="EUR">20.00</Amt></TxAmt></AmtDtls>'
            "<RmtInf><Ustrd>F-2</Ustrd></RmtInf></TxDtls>"
            "</NtryDtls></Ntry>"
        )
        lezing = lees_camt053(_afschrift(entry))
        assert [(b.bedrag, b.omschrijving) for b in lezing.bijschrijvingen] == [
            (Decimal("10.00"), "F-1"),
            (Decimal("20.00"), "F-2"),
        ]

    def test_several_transactions_without_their_own_amount_are_one_credit_with_all_text(
        self,
    ) -> None:
        entry = (
            '<Ntry><Amt Ccy="EUR">30.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts>BOOK</Sts>'
            "<BookgDt><Dt>2026-10-05</Dt></BookgDt><NtryDtls>"
            "<TxDtls><RmtInf><Ustrd>F-1</Ustrd></RmtInf></TxDtls>"
            "<TxDtls><RmtInf><Ustrd>F-2</Ustrd></RmtInf></TxDtls>"
            "</NtryDtls></Ntry>"
        )
        lezing = lees_camt053(_afschrift(entry))
        assert len(lezing.bijschrijvingen) == 1
        assert {"F-1", "F-2"} <= set(lezing.bijschrijvingen[0].omschrijving.split())

    def test_an_entry_without_details_has_an_empty_text(self) -> None:
        entry = '<Ntry><Amt Ccy="EUR">5.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts>BOOK</Sts></Ntry>'
        assert lees_camt053(_afschrift(entry)).bijschrijvingen[0].omschrijving == ""

    def test_control_characters_are_removed_from_the_text(self) -> None:
        # Een tab en een onzichtbaar teken (nul-breedte-spatie): beide zijn geldig in XML 1.0 en moeten eruit.
        lezing = lees_camt053(_afschrift(_entry(omschrijving="F-1&#x9;&#x200B;betaald")))
        assert lezing.bijschrijvingen[0].omschrijving == "F-1betaald"

    def test_the_text_is_cut_to_five_hundred_characters(self) -> None:
        lezing = lees_camt053(_afschrift(_entry(omschrijving="x" * 2000)))
        assert len(lezing.bijschrijvingen[0].omschrijving) == 500

    @pytest.mark.parametrize(
        "bedrag",
        ["abc", "", "NaN", "Infinity", "1e3", "-5.00", "0", "1,5", "12345678901234567890.00"],
    )
    def test_an_unreadable_amount_refuses_the_whole_file(self, bedrag: str) -> None:
        with pytest.raises(BankafschriftFout) as fout:
            lees_camt053(_afschrift(_entry("10.00") + _entry(bedrag)))
        assert fout.value.code == "GEEN_GELDIG_AFSCHRIFT"

    def test_the_message_for_a_bad_amount_does_not_repeat_the_amount_or_text(self) -> None:
        with pytest.raises(BankafschriftFout) as fout:
            lees_camt053(_afschrift(_entry("EEN-RAAR-BEDRAG", "Jan Jansen NL00VOOR0000000001")))
        tekst = fout.value.boodschap + str(fout.value)
        assert "RAAR" not in tekst and "Jansen" not in tekst and "NL00" not in tekst

    def test_a_file_without_a_statement_is_refused(self) -> None:
        data = b'<?xml version="1.0"?><Document><BkToCstmrStmt></BkToCstmrStmt></Document>'
        with pytest.raises(BankafschriftFout):
            lees_camt053(data)

    def test_a_statement_without_entries_is_an_empty_result(self) -> None:
        lezing = lees_camt053(_afschrift(""))
        assert (lezing.bijschrijvingen, lezing.overgeslagen) == ([], 0)

    def test_a_bom_is_accepted(self) -> None:
        assert len(lees_camt053(b"\xef\xbb\xbf" + _afschrift(_entry())).bijschrijvingen) == 1


class TestDeGrenzen:
    def test_a_file_over_the_limit_is_refused_with_its_own_code(self) -> None:
        with pytest.raises(BankafschriftFout) as fout:
            lees_camt053(b"x" * (MAX_BYTES + 1))
        assert (fout.value.code, fout.value.status_code) == ("BESTAND_TE_GROOT", 413)

    def test_a_file_exactly_at_the_limit_is_read_not_refused_for_its_size(self) -> None:
        basis = _afschrift(_entry())
        opvulling = b" " * (MAX_BYTES - len(basis))
        assert len(lees_camt053(basis + opvulling).bijschrijvingen) == 1

    def test_too_many_entries_are_refused(self) -> None:
        with pytest.raises(BankafschriftFout) as fout:
            lees_camt053(_afschrift(_entry() * (MAX_TRANSACTIES + 1)))
        assert fout.value.code == "TE_VEEL_TRANSACTIES"

    def test_exactly_the_maximum_number_of_entries_is_read(self) -> None:
        lezing = lees_camt053(_afschrift(_entry() * MAX_TRANSACTIES))
        assert len(lezing.bijschrijvingen) == MAX_TRANSACTIES

    def test_a_document_nested_too_deep_is_refused(self) -> None:
        diep = "<a>" * 30 + "</a>" * 30
        with pytest.raises(BankafschriftFout):
            lees_camt053(_afschrift(f"<Ntry>{diep}</Ntry>"))

    def test_the_messages_are_dutch_and_say_the_limit(self) -> None:
        with pytest.raises(BankafschriftFout) as fout:
            lees_camt053(b"x" * (MAX_BYTES + 1))
        assert "5 MB" in fout.value.boodschap
