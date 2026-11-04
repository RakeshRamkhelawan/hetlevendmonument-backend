"""Het btw-overzicht per kwartaal uit BEVESTIGDE bonnen (btw-overzicht, 2026-10-19).

Brief `docs/agent-briefs/generated/2026-10-19-sprint-dag-btw-overzicht-uit-bevestigde-bonnen.md`. Het overzicht telt de
voorbelasting (rubriek 5b) per tarief uit alleen de bonnen die een medewerker heeft bevestigd
(`<id>.bevestigd.json`, geen tabel), met `Decimal` en op de cent. Het kwartaal volgt de BONDATUM. Het is geen
omzetbelasting, geen indiening en geen advies.

Afrondingsregel (besluit bouwer, aanname): elk tarief wordt als som van de exacte bedragen op de cent afgerond
(half omhoog); het totaal is de som van de afgeronde delen, zodat het scherm optelt.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.core.als.bonlezer.opruimen import ruim_op
from src.core.als.bonlezer.btw_overzicht import (
    BtwOverzicht,
    Kwartaal,
    huidig_kwartaal,
    kwartaal_uit_pakketinvoer,
    parse_kwartaal,
    vorig_kwartaal,
)

TENANT = 1
ANDERE_TENANT = 2


def _id(teken: str) -> str:
    return teken * 32 + ".pdf"


def _bevestig(
    root: Path,
    tenant: int,
    teken: str,
    datum: object,
    btw: object = None,
    **extra: object,
) -> Path:
    map_ = root / str(tenant)
    map_.mkdir(parents=True, exist_ok=True)
    velden: dict[str, object] = {
        "leverancier": "Bakkerij De Korenaar B.V.",
        "datum": datum,
        "totaal": "12.10",
        "factuurnummer": "F-1",
        "btw": btw if btw is not None else {"9": "0.50", "21": "1.60"},
        "btw_nummer": "NL123456789B01",
        "kvk_nummer": "12345678",
    }
    velden.update(extra)
    pad = map_ / f"{_id(teken)}.bevestigd.json"
    pad.write_text(
        json.dumps({"velden": velden, "door": 1, "bevestigd_op": "2026-10-17T10:00:00+00:00"}),
        encoding="utf-8",
    )
    return pad


def _bevestig_sha(
    root: Path,
    tenant: int,
    teken: str,
    datum: str,
    btw: dict[str, str],
    sha: str | None,
    bevestigd_op: str = "2026-10-17T10:00:00+00:00",
    **extra: object,
) -> Path:
    """Een bevestiging met de sha256 van de bon (de backend legt die vast bij het bevestigen)."""
    pad = _bevestig(root, tenant, teken, datum, btw, **extra)
    record = json.loads(pad.read_text(encoding="utf-8"))
    record["bevestigd_op"] = bevestigd_op
    if sha is not None:
        record["sha256"] = sha
    pad.write_text(json.dumps(record), encoding="utf-8")
    return pad


def _q3() -> Kwartaal:
    return Kwartaal(2026, 3)


class TestKwartaal:
    @pytest.mark.parametrize(
        ("dag", "verwacht"),
        [
            (date(2026, 1, 1), "2026-Q1"),
            (date(2026, 3, 31), "2026-Q1"),
            (date(2026, 4, 1), "2026-Q2"),
            (date(2026, 6, 30), "2026-Q2"),
            (date(2026, 7, 1), "2026-Q3"),
            (date(2026, 9, 30), "2026-Q3"),
            (date(2026, 10, 1), "2026-Q4"),
            (date(2026, 12, 31), "2026-Q4"),
        ],
    )
    def test_the_quarter_of_a_date(self, dag: date, verwacht: str) -> None:
        assert Kwartaal.van(dag).label() == verwacht

    def test_the_first_and_last_day_of_a_quarter(self) -> None:
        k = Kwartaal(2026, 3)

        assert (k.eerste_dag(), k.laatste_dag()) == (date(2026, 7, 1), date(2026, 9, 30))

    def test_the_last_day_of_the_fourth_quarter_is_31_december(self) -> None:
        assert Kwartaal(2026, 4).laatste_dag() == date(2026, 12, 31)

    def test_the_first_quarter_ends_on_31_march(self) -> None:
        assert Kwartaal(2024, 1).laatste_dag() == date(2024, 3, 31)

    def test_the_current_quarter_follows_the_clock(self) -> None:
        nu = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)

        assert huidig_kwartaal(nu) == Kwartaal(2026, 4)

    def test_the_quarter_changes_at_midnight_utc(self) -> None:
        voor = datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)
        na = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)

        assert (huidig_kwartaal(voor), huidig_kwartaal(na)) == (
            Kwartaal(2026, 3),
            Kwartaal(2026, 4),
        )

    @pytest.mark.parametrize(
        ("tekst", "verwacht"),
        [
            ("2026-Q3", Kwartaal(2026, 3)),
            ("2000-Q1", Kwartaal(2000, 1)),
            ("2100-Q4", Kwartaal(2100, 4)),
        ],
    )
    def test_a_valid_label_is_read(self, tekst: str, verwacht: Kwartaal) -> None:
        assert parse_kwartaal(tekst) == verwacht

    @pytest.mark.parametrize(
        "tekst",
        [
            "",
            "2026-Q0",
            "2026-Q5",
            "2026Q3",
            "2026-q3",
            "26-Q3",
            "abcd-Q1",
            "2026-Q3 ",
            "1999-Q1",
            "2101-Q1",
            "2026-Q33",
            None,
            2026,
        ],
    )
    def test_an_invalid_label_is_refused(self, tekst: object) -> None:
        assert parse_kwartaal(tekst) is None

    def test_the_label_round_trips(self) -> None:
        assert parse_kwartaal(Kwartaal(2026, 3).label()) == Kwartaal(2026, 3)


class TestHetOverzicht:
    def _overzicht(
        self, root: Path, tenant: int = TENANT, kwartaal: Kwartaal | None = None
    ) -> dict[str, object]:
        return BtwOverzicht(root).overzicht(tenant, kwartaal or _q3())

    def test_three_bonnen_in_q3_and_one_in_q4_count_only_the_three(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", {"9": "0.50", "21": "1.60"})
        _bevestig(tmp_path, TENANT, "b", "2026-08-20", {"21": "2.10"})
        _bevestig(tmp_path, TENANT, "c", "2026-09-30", {"9": "1.25"})
        _bevestig(tmp_path, TENANT, "d", "2026-10-01", {"9": "99.00", "21": "99.00"})

        uit = self._overzicht(tmp_path)

        assert (uit["aantal"], uit["voorbelasting"], uit["totaal"]) == (
            3,
            {"9": "1.75", "21": "3.70", "overig": "0.00"},
            "5.45",
        )

    def test_the_quarter_label_and_period_are_in_the_answer(self, tmp_path: Path) -> None:
        uit = self._overzicht(tmp_path)

        assert (uit["kwartaal"], uit["van"], uit["tot"]) == ("2026-Q3", "2026-07-01", "2026-09-30")

    def test_the_answer_names_the_rubric_in_plain_language(self, tmp_path: Path) -> None:
        uit = self._overzicht(tmp_path)

        assert (uit["rubriek"], uit["rubriek_naam"]) == ("5b", "Voorbelasting")

    def test_the_first_day_of_the_quarter_counts(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-01")

        assert self._overzicht(tmp_path)["aantal"] == 1

    def test_the_last_day_of_the_quarter_counts(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-09-30")

        assert self._overzicht(tmp_path)["aantal"] == 1

    def test_the_day_before_the_quarter_does_not_count(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-06-30")

        assert self._overzicht(tmp_path)["aantal"] == 0

    def test_the_day_after_the_quarter_does_not_count(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-10-01")

        assert self._overzicht(tmp_path)["aantal"] == 0

    def test_the_same_day_in_another_year_does_not_count(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2025-08-15")

        assert self._overzicht(tmp_path)["aantal"] == 0

    def test_the_quarter_follows_the_bon_date_and_not_the_confirmation_date(
        self, tmp_path: Path
    ) -> None:
        # Bevestigd op 2026-10-17 (Q4), maar de bon is van 2026-08-15 (Q3).
        _bevestig(tmp_path, TENANT, "a", "2026-08-15")

        assert self._overzicht(tmp_path)["aantal"] == 1

    def test_a_bon_that_is_not_confirmed_does_not_count(self, tmp_path: Path) -> None:
        map_ = tmp_path / str(TENANT)
        map_.mkdir()
        (map_ / f"{_id('a')}").write_bytes(b"%PDF-1.4")
        (map_ / f"{_id('a')}.meta.json").write_text("{}", encoding="utf-8")
        (map_ / f"{_id('a')}.resultaat.json").write_text(
            json.dumps(
                {"status": "gelezen", "velden": {"datum": "2026-08-15", "btw": {"21": "5.00"}}}
            ),
            encoding="utf-8",
        )

        uit = self._overzicht(tmp_path)

        assert (uit["aantal"], uit["totaal"]) == (0, "0.00")

    def test_another_tenant_does_not_see_the_overview_of_this_tenant(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-15", {"21": "5.00"})

        uit = self._overzicht(tmp_path, tenant=ANDERE_TENANT)

        assert (uit["aantal"], uit["totaal"]) == (0, "0.00")

    def test_a_confirmation_of_another_tenant_does_not_count_for_this_tenant(
        self, tmp_path: Path
    ) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-15", {"21": "1.00"})
        _bevestig(tmp_path, ANDERE_TENANT, "b", "2026-08-15", {"21": "50.00"})

        assert self._overzicht(tmp_path)["totaal"] == "1.00"

    @pytest.mark.parametrize("tenant", [0, -1, True, "1", None])
    def test_an_invalid_tenant_gives_an_empty_overview(
        self, tmp_path: Path, tenant: object
    ) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-15")

        uit = BtwOverzicht(tmp_path).overzicht(tenant, _q3())  # type: ignore[arg-type]

        assert uit["aantal"] == 0

    def test_a_quarter_without_bonnen_gives_zero_and_no_error(self, tmp_path: Path) -> None:
        uit = self._overzicht(tmp_path)

        assert (
            uit["aantal"],
            uit["aantal_controleren"],
            uit["voorbelasting"],
            uit["totaal"],
        ) == (0, 0, {"9": "0.00", "21": "0.00", "overig": "0.00"}, "0.00")

    def test_a_missing_upload_folder_is_no_error(self, tmp_path: Path) -> None:
        uit = BtwOverzicht(tmp_path / "bestaat-niet").overzicht(TENANT, _q3())

        assert uit["aantal"] == 0

    def test_amounts_are_exact_to_the_cent(self, tmp_path: Path) -> None:
        # Met drijvende komma geeft 0.1 + 0.2 een rest; met Decimal precies 0.30.
        _bevestig(tmp_path, TENANT, "a", "2026-08-01", {"21": "0.10"})
        _bevestig(tmp_path, TENANT, "b", "2026-08-02", {"21": "0.20"})

        assert self._overzicht(tmp_path)["voorbelasting"]["21"] == "0.30"  # type: ignore[index]

    def test_a_half_cent_is_rounded_up(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-01", {"21": "0.005"})

        assert self._overzicht(tmp_path)["voorbelasting"]["21"] == "0.01"  # type: ignore[index]

    def test_a_negative_half_cent_is_rounded_away_from_zero(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-01", {"21": "-0.005"})

        assert self._overzicht(tmp_path)["voorbelasting"]["21"] == "-0.01"  # type: ignore[index]

    def test_the_sum_is_rounded_once_and_not_per_bon(self, tmp_path: Path) -> None:
        # Twee keer 0.0050: per bon afgerond is dat 0.02, de som 0.0100 is 0.01.
        _bevestig(tmp_path, TENANT, "a", "2026-08-01", {"21": "0.0050"})
        _bevestig(tmp_path, TENANT, "b", "2026-08-02", {"21": "0.0050"})

        assert self._overzicht(tmp_path)["voorbelasting"]["21"] == "0.01"  # type: ignore[index]

    def test_the_total_is_the_sum_of_the_rounded_rates(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-01", {"9": "0.005", "21": "0.005"})

        uit = self._overzicht(tmp_path)

        assert (uit["voorbelasting"], uit["totaal"]) == (
            {"9": "0.01", "21": "0.01", "overig": "0.00"},
            "0.02",
        )

    def test_a_credit_note_with_negative_vat_is_subtracted(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-01", {"21": "10.00"})
        _bevestig(tmp_path, TENANT, "b", "2026-08-02", {"21": "-2.50"})

        assert self._overzicht(tmp_path)["voorbelasting"]["21"] == "7.50"  # type: ignore[index]

    def test_other_rates_are_counted_as_other_and_in_the_total(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-01", {"9": "1.00", "6": "0.60", "0": "0.00"})

        uit = self._overzicht(tmp_path)

        assert (uit["voorbelasting"], uit["totaal"]) == (
            {"9": "1.00", "21": "0.00", "overig": "0.60"},
            "1.60",
        )

    def test_a_bon_without_vat_counts_as_a_bon_with_zero_vat(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-01", {})

        uit = self._overzicht(tmp_path)

        assert (uit["aantal"], uit["totaal"]) == (1, "0.00")

    def test_a_confirmation_with_vat_that_is_not_a_dict_is_skipped(self, tmp_path: Path) -> None:
        """Was: telt als 0 btw. Sinds Gate 2 (security) wordt een bon buiten het schema overgeslagen."""
        _bevestig(tmp_path, TENANT, "a", "2026-08-01", "veel")

        uit = self._overzicht(tmp_path)

        assert (uit["aantal"], uit["totaal"]) == (0, "0.00")

    def test_an_amount_that_is_not_a_number_skips_the_bon(self, tmp_path: Path) -> None:
        """Was: het bedrag telt als 0. Een bon waarvan een bedrag geen getal is, wordt niet half geteld."""
        _bevestig(tmp_path, TENANT, "a", "2026-08-01", {"21": "abc", "9": "1.00"})

        uit = self._overzicht(tmp_path)

        assert (uit["aantal"], uit["totaal"]) == (0, "0.00")

    @pytest.mark.parametrize(
        "datum",
        [
            None,
            "",
            "morgen",
            "2026-13-01",
            "2026-02-30",
            20260801,
            "01-08-2026",
            # Python 3.11 leest deze ook als datum; hier zijn ze dat niet (alleen JJJJ-MM-DD).
            "20260801",
            "2026-W31-5",
            "2026-08-01T10:00:00",
            " 2026-08-01",
        ],
    )
    def test_a_confirmation_without_a_readable_date_does_not_count(
        self, tmp_path: Path, datum: object
    ) -> None:
        _bevestig(tmp_path, TENANT, "a", datum)

        assert self._overzicht(tmp_path)["aantal"] == 0

    def test_a_damaged_confirmation_is_skipped(self, tmp_path: Path) -> None:
        map_ = tmp_path / str(TENANT)
        map_.mkdir()
        (map_ / f"{_id('a')}.bevestigd.json").write_text("{kapot", encoding="utf-8")
        _bevestig(tmp_path, TENANT, "b", "2026-08-01", {"21": "1.00"})

        assert self._overzicht(tmp_path)["totaal"] == "1.00"

    def test_a_file_with_another_name_does_not_count(self, tmp_path: Path) -> None:
        map_ = tmp_path / str(TENANT)
        map_.mkdir()
        (map_ / "notities.bevestigd.json").write_text(
            json.dumps({"velden": {"datum": "2026-08-01", "btw": {"21": "50.00"}}}),
            encoding="utf-8",
        )

        assert self._overzicht(tmp_path)["aantal"] == 0

    def test_a_bon_with_remarks_is_counted_for_checking(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-01", kvk_nummer=None)
        _bevestig(tmp_path, TENANT, "b", "2026-08-02")

        uit = self._overzicht(tmp_path)

        assert (uit["aantal"], uit["aantal_controleren"]) == (2, 1)

    def test_a_bon_with_vat_above_the_total_is_counted_for_checking(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-01", {"21": "50.00"}, totaal="1.00")

        assert self._overzicht(tmp_path)["aantal_controleren"] == 1

    def test_the_answer_has_no_names_or_file_ids(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-01")

        tekst = json.dumps(self._overzicht(tmp_path))

        assert "Korenaar" not in tekst and _id("a") not in tekst


class TestDezelfdeBonTweeKeer:
    """Gate 2 (security): dezelfde bon twee keer uploaden en bevestigen mag de voorbelasting niet verdubbelen."""

    def _overzicht(self, root: Path) -> dict[str, object]:
        return BtwOverzicht(root).overzicht(TENANT, _q3())

    def test_a_bon_confirmed_twice_counts_once(self, tmp_path: Path) -> None:
        _bevestig_sha(tmp_path, TENANT, "a", "2026-07-15", {"21": "1.60"}, "s" * 64)
        _bevestig_sha(tmp_path, TENANT, "b", "2026-07-15", {"21": "1.60"}, "s" * 64)

        uit = self._overzicht(tmp_path)

        assert (uit["aantal"], uit["totaal"]) == (1, "1.60")

    def test_the_duplicate_is_reported(self, tmp_path: Path) -> None:
        _bevestig_sha(tmp_path, TENANT, "a", "2026-07-15", {"21": "1.60"}, "s" * 64)
        _bevestig_sha(tmp_path, TENANT, "b", "2026-07-15", {"21": "1.60"}, "s" * 64)

        assert self._overzicht(tmp_path)["aantal_dubbel"] == 1

    def test_three_copies_report_two_duplicates(self, tmp_path: Path) -> None:
        for teken in "abc":
            _bevestig_sha(tmp_path, TENANT, teken, "2026-07-15", {"21": "1.60"}, "s" * 64)

        uit = self._overzicht(tmp_path)

        assert (uit["aantal"], uit["aantal_dubbel"]) == (1, 2)

    def test_the_latest_confirmation_is_the_one_that_counts(self, tmp_path: Path) -> None:
        # Wie een fout ziet en opnieuw bevestigt verbetert zich (besluit regie 2026-10-19).
        _bevestig_sha(
            tmp_path,
            TENANT,
            "a",
            "2026-07-15",
            {"21": "9.00"},
            "s" * 64,
            "2026-10-17T09:00:00+00:00",
        )
        _bevestig_sha(
            tmp_path,
            TENANT,
            "b",
            "2026-07-15",
            {"21": "1.60"},
            "s" * 64,
            "2026-10-17T12:00:00+00:00",
        )

        assert self._overzicht(tmp_path)["totaal"] == "1.60"

    def test_the_latest_counts_whatever_the_file_name_order(self, tmp_path: Path) -> None:
        _bevestig_sha(
            tmp_path,
            TENANT,
            "b",
            "2026-07-15",
            {"21": "9.00"},
            "s" * 64,
            "2026-10-17T09:00:00+00:00",
        )
        _bevestig_sha(
            tmp_path,
            TENANT,
            "a",
            "2026-07-15",
            {"21": "1.60"},
            "s" * 64,
            "2026-10-17T12:00:00+00:00",
        )

        assert self._overzicht(tmp_path)["totaal"] == "1.60"

    def test_a_corrected_confirmation_in_another_quarter_does_not_hide_the_original(
        self, tmp_path: Path
    ) -> None:
        # Dubbel wordt binnen het gekozen kwartaal bepaald: de latere bevestiging met een datum in Q4 valt in Q3 weg.
        _bevestig_sha(tmp_path, TENANT, "a", "2026-07-15", {"21": "1.60"}, "s" * 64)
        _bevestig_sha(
            tmp_path,
            TENANT,
            "b",
            "2026-10-15",
            {"21": "9.00"},
            "s" * 64,
            "2026-10-18T09:00:00+00:00",
        )

        assert self._overzicht(tmp_path)["totaal"] == "1.60"

    def test_different_bonnen_both_count(self, tmp_path: Path) -> None:
        _bevestig_sha(tmp_path, TENANT, "a", "2026-07-15", {"21": "1.60"}, "1" * 64)
        _bevestig_sha(tmp_path, TENANT, "b", "2026-07-15", {"21": "1.60"}, "2" * 64)

        uit = self._overzicht(tmp_path)

        assert (uit["aantal"], uit["aantal_dubbel"], uit["totaal"]) == (2, 0, "3.20")

    def test_confirmations_without_a_hash_both_count(self, tmp_path: Path) -> None:
        _bevestig_sha(tmp_path, TENANT, "a", "2026-07-15", {"21": "1.60"}, None)
        _bevestig_sha(tmp_path, TENANT, "b", "2026-07-15", {"21": "1.60"}, None)

        assert self._overzicht(tmp_path)["aantal"] == 2

    def test_a_copy_in_another_quarter_is_not_merged(self, tmp_path: Path) -> None:
        _bevestig_sha(tmp_path, TENANT, "a", "2026-07-15", {"21": "1.60"}, "s" * 64)
        _bevestig_sha(tmp_path, TENANT, "b", "2026-10-15", {"21": "1.60"}, "s" * 64)

        assert self._overzicht(tmp_path)["aantal"] == 1

    def test_the_same_hash_of_another_tenant_is_no_duplicate(self, tmp_path: Path) -> None:
        _bevestig_sha(tmp_path, TENANT, "a", "2026-07-15", {"21": "1.60"}, "s" * 64)
        _bevestig_sha(tmp_path, ANDERE_TENANT, "b", "2026-07-15", {"21": "1.60"}, "s" * 64)

        uit = self._overzicht(tmp_path)

        assert (uit["aantal"], uit["aantal_dubbel"]) == (1, 0)

    def test_a_quarter_without_duplicates_reports_zero(self, tmp_path: Path) -> None:
        assert self._overzicht(tmp_path)["aantal_dubbel"] == 0


class TestGeenMinnulNul:
    """Gate 2 (code): een som tussen -0,005 en 0 mag niet als -0,00 op het scherm of in de CSV komen."""

    def test_a_tiny_negative_sum_is_zero(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", {"21": "-0.004"})

        uit = BtwOverzicht(tmp_path).overzicht(TENANT, _q3())

        assert (uit["voorbelasting"]["21"], uit["totaal"]) == ("0.00", "0.00")  # type: ignore[index]

    def test_sums_that_cancel_each_other_are_zero(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", {"21": "10.00"})
        _bevestig(tmp_path, TENANT, "b", "2026-07-16", {"21": "-10.00"})

        assert BtwOverzicht(tmp_path).overzicht(TENANT, _q3())["totaal"] == "0.00"

    def test_the_csv_total_has_no_minus_zero(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", {"21": "-0.004"})

        tekst = BtwOverzicht(tmp_path).csv_export(TENANT, _q3())

        laatste = list(csv.reader(io.StringIO(tekst)))[-1]
        assert laatste[4:7] == ["0.00", "0.00", "0.00"]


class TestHetTariefIsEenGetal:
    """Gate 2 (security): 09 en 021 zijn dezelfde tarieven als 9 en 21."""

    def _overzicht(self, root: Path) -> dict[str, object]:
        return BtwOverzicht(root).overzicht(TENANT, _q3())

    def test_a_rate_with_a_leading_zero_counts_as_the_rate(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", {"09": "1.00", "021": "2.00"})

        assert self._overzicht(tmp_path)["voorbelasting"] == {
            "9": "1.00",
            "21": "2.00",
            "overig": "0.00",
        }

    def test_the_same_rate_written_two_ways_adds_up(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", {"9": "1.00", "09": "0.50"})

        assert self._overzicht(tmp_path)["voorbelasting"]["9"] == "1.50"  # type: ignore[index]

    def test_a_zero_rate_stays_in_other(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", {"0": "0.30", "00": "0.20"})

        assert self._overzicht(tmp_path)["voorbelasting"]["overig"] == "0.50"  # type: ignore[index]


class TestEenOngeldigBestandBrengtDeRouteNietOmver:
    """Gate 2 (security): een aangepast bestand (NaN, geen schema) is een overgeslagen bon en geen 500."""

    def _overzicht(self, root: Path) -> dict[str, object]:
        return BtwOverzicht(root).overzicht(TENANT, _q3())

    @pytest.mark.parametrize("totaal", ["NaN", "sNaN", "Infinity", "1e400", "1,5", ""])
    def test_a_total_that_is_not_a_number_is_skipped(self, tmp_path: Path, totaal: str) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", {"21": "1.00"}, totaal=totaal)
        _bevestig(tmp_path, TENANT, "b", "2026-07-16", {"21": "2.00"})

        uit = self._overzicht(tmp_path)

        assert (uit["aantal"], uit["totaal"]) == (1, "2.00")

    def test_vat_that_is_not_a_number_is_skipped(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", {"21": "NaN"})
        _bevestig(tmp_path, TENANT, "b", "2026-07-16", {"21": "2.00"})

        uit = self._overzicht(tmp_path)

        assert (uit["aantal"], uit["totaal"]) == (1, "2.00")

    def test_a_field_outside_the_schema_is_skipped(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", {"21": "1.00"}, onbekend="x")
        _bevestig(tmp_path, TENANT, "b", "2026-07-16", {"21": "2.00"})

        assert self._overzicht(tmp_path)["aantal"] == 1

    def test_the_csv_skips_such_a_file_too(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", {"21": "1.00"}, totaal="NaN")

        tekst = BtwOverzicht(tmp_path).csv_export(TENANT, _q3())

        assert "2026-07-15" not in tekst


class TestDeCsv:
    def _rijen(self, tekst: str) -> list[list[str]]:
        return list(csv.reader(io.StringIO(tekst)))

    def test_the_csv_has_a_header_and_one_row_per_bon_of_the_quarter(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15")
        _bevestig(tmp_path, TENANT, "b", "2026-10-02")

        rijen = self._rijen(BtwOverzicht(tmp_path).csv_export(TENANT, _q3()))

        assert rijen[0][0] == "datum" and [r[0] for r in rijen[1:2]] == ["2026-07-15"]

    def test_a_bon_of_another_quarter_is_not_in_the_csv(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-10-02", leverancier="Q4-leverancier")

        assert "Q4-leverancier" not in BtwOverzicht(tmp_path).csv_export(TENANT, _q3())

    def test_a_bon_of_another_tenant_is_not_in_the_csv(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, ANDERE_TENANT, "a", "2026-08-01", leverancier="Andermans B.V.")

        assert "Andermans" not in BtwOverzicht(tmp_path).csv_export(TENANT, _q3())

    def test_the_csv_ends_with_the_totals_per_rate_and_overall(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", {"9": "0.50", "21": "1.60"})

        laatste = self._rijen(BtwOverzicht(tmp_path).csv_export(TENANT, _q3()))[-1]

        assert laatste[0].startswith("Totaal voorbelasting") and laatste[4:7] == [
            "0.50",
            "1.60",
            "0.00",
        ]

    def test_a_formula_in_the_supplier_is_neutralised(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", leverancier='=HYPERLINK("http://x")')

        rijen = self._rijen(BtwOverzicht(tmp_path).csv_export(TENANT, _q3()))

        assert rijen[1][1].startswith("'=")

    def test_control_characters_are_removed_from_the_csv(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", leverancier="Bak\u202ekerij\x00")

        assert self._rijen(BtwOverzicht(tmp_path).csv_export(TENANT, _q3()))[1][1] == "Bakkerij"

    def test_the_csv_says_which_bonnen_to_check(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15", kvk_nummer=None)

        assert self._rijen(BtwOverzicht(tmp_path).csv_export(TENANT, _q3()))[1][-1] == "ja"

    def test_a_clean_bon_is_not_marked_for_checking(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-07-15")

        assert self._rijen(BtwOverzicht(tmp_path).csv_export(TENANT, _q3()))[1][-1] == "nee"

    def test_the_csv_has_one_row_for_a_bon_that_was_confirmed_twice(self, tmp_path: Path) -> None:
        _bevestig_sha(
            tmp_path,
            TENANT,
            "a",
            "2026-07-15",
            {"21": "1.60"},
            "s" * 64,
            "2026-10-17T10:00:00+00:00",
        )
        _bevestig_sha(
            tmp_path,
            TENANT,
            "b",
            "2026-07-15",
            {"21": "1.60"},
            "s" * 64,
            "2026-10-17T11:00:00+00:00",
        )

        rijen = self._rijen(BtwOverzicht(tmp_path).csv_export(TENANT, _q3()))

        assert (len(rijen), rijen[-1][5]) == (3, "1.60")

    def test_an_empty_quarter_gives_a_header_and_a_zero_total_row(self, tmp_path: Path) -> None:
        rijen = self._rijen(BtwOverzicht(tmp_path).csv_export(TENANT, _q3()))

        assert (len(rijen), rijen[-1][4:7]) == (2, ["0.00", "0.00", "0.00"])


class TestDeBevestigdeVeldenBlijvenNaTienEnDertigDagen:
    """Het overzicht leest de BEVESTIGDE VELDEN, niet de bon: die blijven tot het einde van het kwartaal + 3 maanden.

    Besluit Rakesh 2026-10-17 (optie 2): alleen de bon en zijn metabestand gaan na 30 dagen weg.
    """

    def test_a_bon_of_40_days_old_still_counts_after_the_cleanup(self, tmp_path: Path) -> None:
        pad = _bevestig(tmp_path, TENANT, "a", "2026-10-02", {"21": "1.60"})
        bon = pad.parent / _id("a")
        bon.write_bytes(b"%PDF-1.4")
        veertig_dagen_geleden = datetime(2026, 10, 19, tzinfo=timezone.utc).timestamp() - 40 * 86400
        os.utime(bon, (veertig_dagen_geleden, veertig_dagen_geleden))

        verwijderd = ruim_op(tmp_path, nu=datetime(2026, 10, 19, tzinfo=timezone.utc))

        uit = BtwOverzicht(tmp_path).overzicht(TENANT, Kwartaal(2026, 4))
        assert (verwijderd, bon.exists(), uit["aantal"], uit["totaal"]) == (
            {TENANT: 1},
            False,
            1,
            "1.60",
        )


class TestHetVorigeKwartaalEnDeInvoerVanHetPakket:
    """Zero-admin afwerken: stap 1 en 2 gebruiken DEZELFDE kwartaalregel (aangifte doe je achteraf)."""

    @pytest.mark.parametrize(
        ("nu", "verwacht"),
        [
            (datetime(2026, 10, 19, tzinfo=timezone.utc), "2026-Q3"),
            (datetime(2026, 1, 1, tzinfo=timezone.utc), "2025-Q4"),
            (datetime(2026, 3, 31, 23, 59, tzinfo=timezone.utc), "2025-Q4"),
            (datetime(2026, 4, 1, tzinfo=timezone.utc), "2026-Q1"),
            (datetime(2026, 12, 31, tzinfo=timezone.utc), "2026-Q3"),
        ],
    )
    def test_the_previous_closed_quarter(self, nu: datetime, verwacht: str) -> None:
        assert vorig_kwartaal(nu).label() == verwacht

    def test_without_a_quarter_in_the_input_the_previous_closed_quarter_is_used(self) -> None:
        nu = datetime(2026, 10, 19, tzinfo=timezone.utc)

        assert kwartaal_uit_pakketinvoer({"invoer": "iets"}, nu) == (Kwartaal(2026, 3), None)

    def test_no_input_at_all_gives_the_previous_closed_quarter(self) -> None:
        nu = datetime(2026, 10, 19, tzinfo=timezone.utc)

        assert kwartaal_uit_pakketinvoer(None, nu) == (Kwartaal(2026, 3), None)

    def test_a_quarter_key_decides(self) -> None:
        nu = datetime(2026, 10, 19, tzinfo=timezone.utc)

        assert kwartaal_uit_pakketinvoer({"kwartaal": "2026-Q1"}, nu) == (Kwartaal(2026, 1), None)

    def test_free_text_never_decides_the_quarter(self) -> None:
        nu = datetime(2026, 10, 19, tzinfo=timezone.utc)

        kwartaal, _ = kwartaal_uit_pakketinvoer({"invoer": "2026-Q1"}, nu)

        assert kwartaal == Kwartaal(2026, 3)

    @pytest.mark.parametrize("kapot", ["2026-Q5", "morgen", "", 2026, None])
    def test_an_invalid_quarter_key_is_an_error_in_dutch(self, kapot: object) -> None:
        nu = datetime(2026, 10, 19, tzinfo=timezone.utc)

        kwartaal, fout = kwartaal_uit_pakketinvoer({"kwartaal": kapot}, nu)

        assert kwartaal is None and fout is not None and "kwartaal" in fout.lower()


class TestDeBonnenSamenvattingVanEenKwartaal:
    """Stap 1 telt hetzelfde kwartaal als stap 2: dezelfde bonnen, dezelfde ontdubbeling, hetzelfde aantal."""

    def _samenvatting(self, root: Path) -> dict[str, object]:
        return BtwOverzicht(root).bonnen_samenvatting(TENANT, _q3())

    def test_only_the_bonnen_of_the_quarter_count(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-05")
        _bevestig(tmp_path, TENANT, "b", "2026-10-05")

        assert self._samenvatting(tmp_path)["aantal"] == 1

    def test_it_names_the_quarter(self, tmp_path: Path) -> None:
        assert self._samenvatting(tmp_path)["kwartaal"] == "2026-Q3"

    def test_total_and_vat_per_rate_are_summed_to_the_cent(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, TENANT, "a", "2026-08-05", {"9": "0.50", "21": "1.60"})
        _bevestig(tmp_path, TENANT, "b", "2026-08-06", {"21": "2.10"})

        uit = self._samenvatting(tmp_path)

        assert (uit["totaal"], uit["btw"]) == ("24.20", {"9": "0.50", "21": "3.70"})

    def test_a_bon_confirmed_twice_counts_once_like_in_the_overview(self, tmp_path: Path) -> None:
        _bevestig_sha(tmp_path, TENANT, "a", "2026-08-05", {"21": "1.60"}, "s" * 64)
        _bevestig_sha(tmp_path, TENANT, "b", "2026-08-05", {"21": "1.60"}, "s" * 64)

        assert self._samenvatting(tmp_path)["aantal"] == 1

    def test_the_count_equals_the_count_of_the_overview(self, tmp_path: Path) -> None:
        for teken, datum in (("a", "2026-07-01"), ("b", "2026-09-30"), ("c", "2026-10-01")):
            _bevestig(tmp_path, TENANT, teken, datum)

        samenvatting = self._samenvatting(tmp_path)
        overzicht = BtwOverzicht(tmp_path).overzicht(TENANT, _q3())

        assert samenvatting["aantal"] == overzicht["aantal"] == 2

    def test_another_tenant_does_not_count(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, ANDERE_TENANT, "a", "2026-08-05")

        assert self._samenvatting(tmp_path)["aantal"] == 0

    def test_an_empty_quarter_is_zero(self, tmp_path: Path) -> None:
        uit = self._samenvatting(tmp_path)

        assert (uit["aantal"], uit["totaal"], uit["btw"]) == (0, "0.00", {})
