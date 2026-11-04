"""De tijdlijn van een factuur -- debiteuren vanzelf afronden, B4 (2026-10-20).

`bouw_tijdlijn` maakt uit gewone gegevens (geen database) de gebeurtenissen van een factuur: aangemaakt, voorgesteld
door, goedgekeurd door, verstuurd (of niet verstuurd, met de reden), betaald en geescaleerd, oudste eerst, met datum en
de naam (het e-mailadres) van de medewerker, in het Nederlands. Gemeten:

1. Elke stap staat erin met tijdstip en naam; de volgorde is die van de tijd, ook als de bronnen door elkaar liggen.
2. Een medewerker die niet meer bestaat krijgt een eerlijke tekst, geen verzonnen naam en geen kaal nummer.
3. Een geannuleerd bericht zegt waarom; een afgekeurd ticket noemt de notitie van de mens.
4. Betaald via het afschrift en met de hand zijn te onderscheiden; een oudere betaalde factuur zonder auditregel staat
   er toch als betaald.
5. Er staat geen e-mailadres van de debiteur, geen brieftekst en geen tekst uit een bankafschrift in.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.core.services.debiteur_tijdlijn import (
    ONBEKENDE_MEDEWERKER,
    AuditBron,
    BerichtBron,
    Bronnen,
    TicketBron,
    bouw_tijdlijn,
)


def _t(dag: int, uur: int = 9) -> datetime:
    return datetime(2026, 10, dag, uur, 0, tzinfo=timezone.utc)


def _bronnen(**extra: object) -> Bronnen:
    basis: dict[str, object] = {
        "created_at": _t(1),
        "status": "open",
        "betaald_op": None,
        "namen": {1: "anna@bedrijf.example", 2: "bram@bedrijf.example"},
    }
    basis.update(extra)
    return Bronnen(**basis)  # type: ignore[arg-type]


def _audit(soort: str, dag: int, user_id: int | None = 1, **metadata: object) -> AuditBron:
    resource = "/api/v1/receivables/7"
    if soort.startswith("debiteuren_bericht"):
        resource = "outgoing_message:5"
    if soort == "debiteuren_dossier_geescaleerd":
        resource = "receivable:7"
    return AuditBron(soort, resource, _t(dag), user_id, dict(metadata))


def _bericht(status: str = "klaar", **extra: object) -> BerichtBron:
    basis: dict[str, object] = {
        "id": 5,
        "kind": "herinnering",
        "status": status,
        "pogingen": 0,
        "foutreden": None,
        "created_at": _t(3),
        "verzonden_op": None,
        "hitl_ticket_ref": "TOOL-AB12",
    }
    basis.update(extra)
    return BerichtBron(**basis)  # type: ignore[arg-type]


def _teksten(bronnen: Bronnen) -> list[str]:
    return [g.tekst for g in bouw_tijdlijn(bronnen)]


class TestDeStappen:
    def test_a_new_invoice_has_only_its_creation(self) -> None:
        assert _teksten(_bronnen()) == ["Factuur aangemaakt"]

    def test_the_creator_is_named_when_the_audit_line_is_known(self) -> None:
        bronnen = _bronnen(audits=[_audit("receivable_created", 1, 1)])

        assert _teksten(bronnen) == ["Factuur aangemaakt door anna@bedrijf.example"]

    def test_a_proposal_names_the_proposer_and_the_kind(self) -> None:
        bronnen = _bronnen(
            audits=[_audit("receivable_reminder_proposed", 2, 2, kind="aanmaning", ticket_ref="T1")]
        )

        assert "Aanmaning voorgesteld door bram@bedrijf.example" in _teksten(bronnen)

    def test_an_approval_names_the_approver_and_the_time(self) -> None:
        bronnen = _bronnen(
            audits=[
                _audit("receivable_reminder_proposed", 2, 1, kind="herinnering", ticket_ref="T1")
            ],
            tickets=[TicketBron("T1", "approved", 2, _t(2, 15), None)],
        )

        gebeurtenis = [g for g in bouw_tijdlijn(bronnen) if g.soort == "goedgekeurd"][0]

        assert (gebeurtenis.tekst, gebeurtenis.tijdstip) == (
            "Goedgekeurd door bram@bedrijf.example",
            _t(2, 15),
        )

    def test_a_consumed_ticket_still_counts_as_approved(self) -> None:
        bronnen = _bronnen(
            berichten=[_bericht()], tickets=[TicketBron("TOOL-AB12", "consumed", 2, _t(3), None)]
        )

        assert "Goedgekeurd door bram@bedrijf.example" in _teksten(bronnen)

    def test_a_rejection_names_the_note_of_the_person(self) -> None:
        bronnen = _bronnen(
            audits=[
                _audit("receivable_reminder_proposed", 2, 1, kind="herinnering", ticket_ref="T1")
            ],
            tickets=[TicketBron("T1", "rejected", 2, _t(2, 12), "klant belt eerst terug")],
        )

        assert "Afgekeurd door bram@bedrijf.example: klant belt eerst terug" in _teksten(bronnen)

    def test_a_pending_ticket_adds_no_decision(self) -> None:
        bronnen = _bronnen(
            audits=[
                _audit("receivable_reminder_proposed", 2, 1, kind="herinnering", ticket_ref="T1")
            ],
            tickets=[TicketBron("T1", "pending", None, None, None)],
        )

        assert [g.soort for g in bouw_tijdlijn(bronnen)] == ["aangemaakt", "voorgesteld"]

    def test_a_ticket_of_another_invoice_is_ignored(self) -> None:
        bronnen = _bronnen(tickets=[TicketBron("ANDERS", "approved", 2, _t(2), None)])

        assert _teksten(bronnen) == ["Factuur aangemaakt"]

    def test_a_sent_letter_has_its_sending_time(self) -> None:
        bronnen = _bronnen(berichten=[_bericht("verzonden", verzonden_op=_t(4, 10))])

        verzonden = [g for g in bouw_tijdlijn(bronnen) if g.soort == "verzonden"][0]

        assert (verzonden.tekst, verzonden.tijdstip) == ("Herinnering verzonden", _t(4, 10))

    def test_a_ready_letter_is_not_yet_sent(self) -> None:
        bronnen = _bronnen(berichten=[_bericht("klaar")])

        assert _teksten(bronnen) == ["Factuur aangemaakt", "Herinnering klaargezet voor verzending"]

    def test_a_cancelled_letter_says_why(self) -> None:
        reden = "de factuur is betaald of staat niet meer open, dus de brief is niet verstuurd."
        bronnen = _bronnen(
            berichten=[_bericht("mislukt", pogingen=3, foutreden=f"Geannuleerd: {reden}")],
            audits=[_audit("debiteuren_bericht_geannuleerd", 5, None)],
        )

        geannuleerd = [g for g in bouw_tijdlijn(bronnen) if g.soort == "geannuleerd"][0]

        assert (geannuleerd.tekst, geannuleerd.tijdstip) == (
            f"Herinnering niet verstuurd: {reden}",
            _t(5),
        )

    def test_a_failed_letter_is_not_called_cancelled(self) -> None:
        bronnen = _bronnen(
            berichten=[_bericht("mislukt", pogingen=2, foutreden="mailserver weigert")]
        )

        assert "Herinnering versturen mislukt (poging 2 van de 3)" in _teksten(bronnen)

    def test_an_escalation_is_listed(self) -> None:
        bronnen = _bronnen(audits=[_audit("debiteuren_dossier_geescaleerd", 20, None)])

        assert "Dossier geescaleerd: de factuur is niet op tijd betaald" in _teksten(bronnen)


class TestBetaald:
    def test_paid_via_the_statement_is_told_apart(self) -> None:
        bronnen = _bronnen(
            status="betaald",
            betaald_op=_t(6),
            audits=[_audit("receivable_paid_via_bankstatement", 7, 1)],
        )

        betaald = [g for g in bouw_tijdlijn(bronnen) if g.soort == "betaald"]

        assert [(g.tekst, g.tijdstip) for g in betaald] == [
            ("Betaald, afgevinkt via een bankafschrift", _t(6))
        ]

    def test_paid_by_hand_names_the_person(self) -> None:
        bronnen = _bronnen(
            status="betaald",
            betaald_op=_t(6),
            audits=[
                _audit("receivable_status_changed", 6, 2, old_status="open", new_status="betaald")
            ],
        )

        assert "Op betaald gezet door bram@bedrijf.example" in _teksten(bronnen)

    def test_a_change_to_another_status_is_not_a_payment(self) -> None:
        bronnen = _bronnen(
            audits=[
                _audit("receivable_status_changed", 6, 2, old_status="betaald", new_status="open")
            ]
        )

        assert [g.soort for g in bouw_tijdlijn(bronnen)] == ["aangemaakt"]

    def test_an_older_paid_invoice_without_audit_line_is_still_listed_as_paid(self) -> None:
        bronnen = _bronnen(status="betaald", betaald_op=_t(6))

        assert _teksten(bronnen) == ["Factuur aangemaakt", "Betaald"]

    def test_an_open_invoice_is_not_listed_as_paid(self) -> None:
        assert "Betaald" not in _teksten(_bronnen(status="open"))


class TestVolgordeEnNamen:
    def test_the_events_are_in_the_order_of_time(self) -> None:
        bronnen = _bronnen(
            status="betaald",
            betaald_op=_t(9),
            audits=[
                _audit("receivable_status_changed", 9, 1, new_status="betaald"),
                _audit("receivable_reminder_proposed", 2, 1, kind="herinnering", ticket_ref="T1"),
            ],
            berichten=[_bericht("verzonden", verzonden_op=_t(4), hitl_ticket_ref="T1")],
            tickets=[TicketBron("T1", "approved", 2, _t(3), None)],
        )

        assert [g.soort for g in bouw_tijdlijn(bronnen)] == [
            "aangemaakt",
            "voorgesteld",
            "goedgekeurd",
            "klaargezet",
            "verzonden",
            "betaald",
        ]

    def test_a_missing_user_gets_an_honest_text_and_no_number(self) -> None:
        bronnen = _bronnen(audits=[_audit("receivable_created", 1, 99)])

        tekst = _teksten(bronnen)[0]

        assert (ONBEKENDE_MEDEWERKER in tekst, "99" in tekst) == (True, False)

    def test_an_event_without_a_time_comes_last(self) -> None:
        bronnen = _bronnen(status="betaald", betaald_op=None)

        assert [g.soort for g in bouw_tijdlijn(bronnen)] == ["aangemaakt", "betaald"]

    def test_all_texts_are_ascii(self) -> None:
        bronnen = _bronnen(
            status="betaald",
            betaald_op=_t(9),
            audits=[_audit("debiteuren_dossier_geescaleerd", 8, None)],
            berichten=[_bericht("mislukt", pogingen=1, foutreden="x")],
        )

        assert all(t.isascii() for t in _teksten(bronnen))


class TestNotitie:
    """De vrije notitie van een mens kan persoonsgegevens of brieftekst bevatten (Gate 2 ronde 1): hij wordt afgekapt."""

    def test_a_long_note_is_cut_to_two_hundred_characters(self) -> None:
        bronnen = _bronnen(
            audits=[
                _audit("receivable_reminder_proposed", 2, 1, kind="herinnering", ticket_ref="T1")
            ],
            tickets=[TicketBron("T1", "rejected", 2, _t(2, 12), "x" * 500)],
        )

        tekst = [g.tekst for g in bouw_tijdlijn(bronnen) if g.soort == "afgekeurd"][0]

        assert tekst == "Afgekeurd door bram@bedrijf.example: " + "x" * 200 + "..."

    def test_a_short_note_is_kept_whole(self) -> None:
        bronnen = _bronnen(
            audits=[
                _audit("receivable_reminder_proposed", 2, 1, kind="herinnering", ticket_ref="T1")
            ],
            tickets=[TicketBron("T1", "rejected", 2, _t(2, 12), "klant belt terug")],
        )

        assert "Afgekeurd door bram@bedrijf.example: klant belt terug" in _teksten(bronnen)


class TestGeannuleerdZonderAuditregel:
    """Acceptatie 2026-10-21: een brief die bij `PATCH` naar betaald wordt geannuleerd heeft geen eigen auditregel en
    stond als "datum onbekend". De annulering gebeurt op het moment van betalen: `betaald_op` is dan het tijdstip."""

    _REDEN = "Geannuleerd: de factuur is betaald of staat niet meer open, dus de brief is niet verstuurd."

    def test_the_payment_time_is_used_when_there_is_no_audit_line(self) -> None:
        bronnen = _bronnen(
            status="betaald",
            betaald_op=_t(6),
            berichten=[_bericht("mislukt", pogingen=3, foutreden=self._REDEN)],
        )

        geannuleerd = [g for g in bouw_tijdlijn(bronnen) if g.soort == "geannuleerd"][0]

        assert geannuleerd.tijdstip == _t(6)

    def test_an_audit_line_still_wins_over_the_payment_time(self) -> None:
        bronnen = _bronnen(
            status="betaald",
            betaald_op=_t(6),
            berichten=[_bericht("mislukt", pogingen=3, foutreden=self._REDEN)],
            audits=[_audit("debiteuren_bericht_geannuleerd", 7, None)],
        )

        geannuleerd = [g for g in bouw_tijdlijn(bronnen) if g.soort == "geannuleerd"][0]

        assert geannuleerd.tijdstip == _t(7)

    def test_a_failed_letter_never_borrows_the_payment_time(self) -> None:
        bronnen = _bronnen(
            status="betaald",
            betaald_op=_t(6),
            berichten=[_bericht("mislukt", pogingen=2, foutreden="mailserver weigert")],
        )

        mislukt = [g for g in bouw_tijdlijn(bronnen) if g.soort == "mislukt"][0]

        assert mislukt.tijdstip is None
