"""Het SEPA-betaalbestand valideert tegen het schema pain.001.001.09 (crediteuren dag 3, Keten F).

De structuurtests in `tests/unit/services/test_sepa_betaalbestand.py` meten wat de bouwer verwacht; deze test meet wat het SCHEMA
eist (elementvolgorde, verplichte velden, lengtes, patronen). Het schemabestand staat ongewijzigd in `tests/fixtures/iso20022/`;
herkomst en sha256 staan in de commitboodschap van dat bestand. Een bank of een andere bank-versie kan strenger zijn: dat is niet
gemeten.

Mutatiebewijs: een bestand met twee elementen in de verkeerde volgorde (zie `test_the_schema_rejects_elements_in_the_wrong_order`)
wordt door dezelfde functie geweigerd, anders zou deze test niets bewaken.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import xmlschema

from src.core.services.sepa_betaalbestand import BetaalRegel, Betaalopdracht, maak_pain001

XSD = Path(__file__).resolve().parents[1] / "fixtures" / "iso20022" / "pain.001.001.09.xsd"


@pytest.fixture(scope="module")
def schema() -> xmlschema.XMLSchema11:
    return xmlschema.XMLSchema11(str(XSD))


def _regel(nummer: int, **over: object) -> BetaalRegel:
    basis: dict[str, object] = {
        "payable_id": nummer,
        "naam": "Drukkerij Van Dijk BV",
        "iban": "NL02ABNA0123456789",
        "bedrag_cents": 121000,
        "factuurnummer": f"INK-2026-{nummer:04d}",
    }
    basis.update(over)
    return BetaalRegel(**basis)  # type: ignore[arg-type]


def _opdracht(regels: list[BetaalRegel], **over: object) -> Betaalopdracht:
    basis: dict[str, object] = {
        "bericht_id": "hitl_0123456789abcdef",
        "gemaakt_op": datetime(2026, 10, 25, 12, 30, 15, 123456, tzinfo=timezone.utc),
        "uitvoerdatum": date(2026, 10, 27),
        "debiteur_naam": "Mijn Bedrijf BV",
        "debiteur_iban": "NL91ABNA0417164300",
        "regels": regels,
    }
    basis.update(over)
    return Betaalopdracht(**basis)  # type: ignore[arg-type]


def _fouten(schema: xmlschema.XMLSchema11, inhoud: bytes) -> list[str]:
    return [str(f.reason) for f in schema.iter_errors(inhoud)]


def test_the_schema_file_is_the_pain_001_001_09_schema(schema: xmlschema.XMLSchema11) -> None:
    assert schema.target_namespace == "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"


def test_a_file_with_one_payment_is_valid(schema: xmlschema.XMLSchema11) -> None:
    assert _fouten(schema, maak_pain001(_opdracht([_regel(1)]), vandaag=date(2026, 10, 26))) == []


def test_a_file_with_many_payments_is_valid(schema: xmlschema.XMLSchema11) -> None:
    regels = [_regel(n, bedrag_cents=n * 1999 + 1) for n in range(1, 101)]

    assert _fouten(schema, maak_pain001(_opdracht(regels), vandaag=date(2026, 10, 26))) == []


def test_a_file_with_special_characters_and_the_longest_names_is_valid(
    schema: xmlschema.XMLSchema11,
) -> None:
    regel = _regel(1, naam="Bj\u00f8rn & S\u00f8nner \u00c6ble \u0141\u00f3d\u017a " * 6, factuurnummer="F/2026-1 (a+b)?" * 5)

    assert _fouten(schema, maak_pain001(_opdracht([regel]), vandaag=date(2026, 10, 26))) == []


def test_a_file_with_cents_and_a_large_amount_is_valid(schema: xmlschema.XMLSchema11) -> None:
    regels = [_regel(1, bedrag_cents=1), _regel(2, bedrag_cents=99999999999)]

    assert _fouten(schema, maak_pain001(_opdracht(regels), vandaag=date(2026, 10, 26))) == []


def test_the_schema_rejects_elements_in_the_wrong_order(schema: xmlschema.XMLSchema11) -> None:
    inhoud = maak_pain001(_opdracht([_regel(1)]), vandaag=date(2026, 10, 26)).decode("utf-8")
    kop = "<NbOfTxs>1</NbOfTxs>"
    assert kop in inhoud, "de mutatie vindt zijn aanknopingspunt niet meer"
    verkeerd = inhoud.replace(kop, "", 1).replace("<MsgId>", kop + "<MsgId>", 1)

    assert _fouten(schema, verkeerd.encode("utf-8")) != []


def test_the_schema_rejects_a_file_without_a_debtor_account(schema: xmlschema.XMLSchema11) -> None:
    inhoud = maak_pain001(_opdracht([_regel(1)]), vandaag=date(2026, 10, 26)).decode("utf-8")
    begin, einde = inhoud.index("<DbtrAcct>"), inhoud.index("</DbtrAcct>") + len("</DbtrAcct>")

    assert _fouten(schema, (inhoud[:begin] + inhoud[einde:]).encode("utf-8")) != []
