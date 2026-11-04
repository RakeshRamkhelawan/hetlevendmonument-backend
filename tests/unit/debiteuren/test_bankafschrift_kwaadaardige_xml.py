"""Kwaadaardige XML in een bankafschrift wordt geweigerd -- debiteuren vanzelf afronden, B2 (2026-10-20).

Een bankafschrift komt van de gebruiker en is dus onbetrouwbare invoer. De brief vraagt "defusedxml of gelijkwaardig";
er komt GEEN nieuwe dependency bij: `lees_camt053` weigert elk document met een `<!DOCTYPE` of `<!ENTITY` (een echt
CAMT.053-bestand heeft er nooit een) VOOR het parsen, leest alleen UTF-8 en heeft grenzen. Wat hier gemeten wordt:

1. Miljard-lachen, een extern bestand, een parameter-entiteit en elke andere DOCTYPE of ENTITY (ook in hoofd- of
   kleine letters en in een commentaar): geweigerd, snel.
2. Een andere codering dan UTF-8 (ook UTF-16, waarmee een DOCTYPE zich voor een bytezoeker zou verstoppen): geweigerd.
3. Kapotte, lege en niet-afschriftbestanden: geweigerd.
4. De foutmelding herhaalt NOOIT iets uit het bestand (persoonsgegevens).

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import time

import pytest

from src.core.services.bankafschrift import BankafschriftFout, lees_camt053

MILJARD_LACHEN = (
    b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
    b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
    b'<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">'
    b'<!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">]>'
    b"<Document><BkToCstmrStmt><Stmt><Id>&lol4;</Id></Stmt></BkToCstmrStmt></Document>"
)
EXTERN_BESTAND = (
    b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///geheim/bestand.txt">]>'
    b"<Document><BkToCstmrStmt><Stmt><Id>&x;</Id></Stmt></BkToCstmrStmt></Document>"
)
GOED_ZONDER_KOP = b"<Document><BkToCstmrStmt><Stmt><Id>S1</Id></Stmt></BkToCstmrStmt></Document>"


def test_an_entity_bomb_is_refused_quickly() -> None:
    start = time.perf_counter()
    with pytest.raises(BankafschriftFout):
        lees_camt053(MILJARD_LACHEN)
    assert time.perf_counter() - start < 1.0


def test_an_external_entity_is_refused() -> None:
    with pytest.raises(BankafschriftFout) as fout:
        lees_camt053(EXTERN_BESTAND)
    assert fout.value.code == "GEEN_GELDIG_AFSCHRIFT"


@pytest.mark.parametrize(
    "kop",
    [
        b"<!DOCTYPE x>",
        b"<!doctype x>",
        b"<!DocType x [ ]>",
        b'<!DOCTYPE x [<!ENTITY % p SYSTEM "http://127.0.0.1/x.dtd"> %p;]>',
        b'<!DOCTYPE x [<!ENTITY a "b">]>',
        b'<!ENTITY a "b">',
    ],
)
def test_any_doctype_or_entity_declaration_is_refused(kop: bytes) -> None:
    with pytest.raises(BankafschriftFout):
        lees_camt053(b'<?xml version="1.0"?>' + kop + GOED_ZONDER_KOP)


def test_a_doctype_inside_a_comment_is_refused_too() -> None:
    data = (
        b"<Document><!-- <!DOCTYPE x> --><BkToCstmrStmt><Stmt><Id>S1</Id></Stmt>"
        b"</BkToCstmrStmt></Document>"
    )
    with pytest.raises(BankafschriftFout):
        lees_camt053(data)


def test_a_file_without_a_doctype_is_read() -> None:
    assert lees_camt053(GOED_ZONDER_KOP).bijschrijvingen == []


def test_utf16_with_a_doctype_is_refused_because_only_utf8_is_read() -> None:
    tekst = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x [<!ENTITY a "b">]><Document/>'
    with pytest.raises(BankafschriftFout):
        lees_camt053(tekst.encode("utf-16"))


def test_a_declared_latin1_encoding_is_refused() -> None:
    data = (
        b'<?xml version="1.0" encoding="ISO-8859-1"?>'
        b"<Document><BkToCstmrStmt><Stmt><Id>S</Id></Stmt></BkToCstmrStmt></Document>"
    )
    with pytest.raises(BankafschriftFout):
        lees_camt053(data)


def test_a_declared_utf8_encoding_in_any_case_is_read() -> None:
    data = b'<?xml version="1.0" encoding="utf-8"?>' + GOED_ZONDER_KOP
    assert lees_camt053(data).bijschrijvingen == []


def test_bytes_that_are_not_utf8_are_refused() -> None:
    with pytest.raises(BankafschriftFout):
        lees_camt053(b'<?xml version="1.0"?><Document>\xff\xfe\xfa</Document>')


@pytest.mark.parametrize(
    "data", [b"", b"   ", b"geen xml", b"<Document>", b"<a><b></a>", b"\x00\x01\x02"]
)
def test_broken_or_empty_files_are_refused(data: bytes) -> None:
    with pytest.raises(BankafschriftFout):
        lees_camt053(data)


def test_something_that_is_not_a_statement_is_refused() -> None:
    with pytest.raises(BankafschriftFout):
        lees_camt053(b"<html><body>hallo</body></html>")


def test_the_message_never_repeats_what_is_in_the_file() -> None:
    with pytest.raises(BankafschriftFout) as fout:
        lees_camt053(EXTERN_BESTAND)
    tekst = fout.value.boodschap + str(fout.value)
    assert "bestand.txt" not in tekst and "lolz" not in tekst and "file://" not in tekst


def test_the_refusal_is_in_dutch() -> None:
    with pytest.raises(BankafschriftFout) as fout:
        lees_camt053(EXTERN_BESTAND)
    assert "afschrift" in fout.value.boodschap.lower()
