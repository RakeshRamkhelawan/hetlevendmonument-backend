"""Bonlezer dag 4, besluit Rakesh 2026-10-17 ("optie 2"): de BEVESTIGDE velden blijven bewaard tot het einde
van het kwartaal van de bondatum plus 3 maanden en worden daarna door de dagelijkse opruiming verwijderd.

Dit is het akkoord (interlock 1) voor DEZE automatische verwijdering en voor niets anders: de bon en zijn
metabestanden blijven op 30 dagen (`test_opruimen.py`). Daarom toetsen deze tests vooral wat er NIET weg mag:
een bevestiging die nog binnen de termijn valt, een bestand zonder leesbare bondatum, andere tenants, en
alles wat geen bevestiging is.

De termijn: bondatum 2026-02-26 valt in kwartaal 1 (einde 2026-03-31); plus 3 maanden is 2026-06-30. Op die dag
staat de bevestiging er nog, op 2026-07-01 niet meer.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.core.als.bonlezer.opruimen import bewaar_tot, ruim_bevestigd_op

ID_A = "a" * 32 + ".pdf"
ID_B = "b" * 32 + ".jpg"


def _dag(jaar: int, maand: int, dag: int) -> datetime:
    return datetime(jaar, maand, dag, 12, 0, tzinfo=timezone.utc)


def _bevestig(root: Path, tenant: int, bestand_id: str, datum: object) -> Path:
    map_ = root / str(tenant)
    map_.mkdir(parents=True, exist_ok=True)
    pad = map_ / f"{bestand_id}.bevestigd.json"
    pad.write_text(
        json.dumps({"velden": {"datum": datum, "totaal": "12.10"}, "door": 1}), encoding="utf-8"
    )
    return pad


class TestDeTermijn:
    @pytest.mark.parametrize(
        ("datum", "verwacht"),
        [
            ("2026-02-26", "2026-06-30"),
            ("2026-01-01", "2026-06-30"),
            ("2026-03-31", "2026-06-30"),
            ("2026-04-01", "2026-09-30"),
            ("2026-06-30", "2026-09-30"),
            ("2026-07-01", "2026-12-31"),
            ("2026-09-30", "2026-12-31"),
            ("2026-10-01", "2027-03-31"),
            ("2026-12-15", "2027-03-31"),
            ("2024-02-29", "2024-06-30"),
        ],
    )
    def test_the_end_of_the_quarter_plus_three_months(self, datum: str, verwacht: str) -> None:
        eind = bewaar_tot(datum)

        assert eind is not None and eind.isoformat() == verwacht

    @pytest.mark.parametrize(
        "onzin", ["", "morgen", "2026-13-01", "2026-02-30", None, 20260226, "26-02-2026"]
    )
    def test_an_unreadable_date_has_no_term(self, onzin: object) -> None:
        assert bewaar_tot(onzin) is None


class TestWatWegMag:
    def test_a_confirmation_on_the_last_day_of_the_term_stays(self, tmp_path: Path) -> None:
        pad = _bevestig(tmp_path, 1, ID_A, "2026-02-26")

        ruim_bevestigd_op(tmp_path, nu=_dag(2026, 6, 30))

        assert pad.exists()

    def test_a_confirmation_the_day_after_the_term_is_removed(self, tmp_path: Path) -> None:
        pad = _bevestig(tmp_path, 1, ID_A, "2026-02-26")

        ruim_bevestigd_op(tmp_path, nu=_dag(2026, 7, 1))

        assert not pad.exists()

    def test_a_bon_on_the_last_day_of_a_quarter_belongs_to_that_quarter(
        self, tmp_path: Path
    ) -> None:
        pad = _bevestig(tmp_path, 1, ID_A, "2026-03-31")

        ruim_bevestigd_op(tmp_path, nu=_dag(2026, 7, 1))

        assert not pad.exists()

    def test_a_bon_on_the_first_day_of_a_quarter_belongs_to_the_next_one(
        self, tmp_path: Path
    ) -> None:
        pad = _bevestig(tmp_path, 1, ID_A, "2026-04-01")

        ruim_bevestigd_op(tmp_path, nu=_dag(2026, 7, 1))

        assert pad.exists()

    def test_the_fourth_quarter_runs_into_the_next_year(self, tmp_path: Path) -> None:
        pad = _bevestig(tmp_path, 1, ID_A, "2026-12-15")

        ruim_bevestigd_op(tmp_path, nu=_dag(2027, 3, 31))

        assert pad.exists()

    def test_the_fourth_quarter_goes_away_the_day_after_in_the_next_year(
        self, tmp_path: Path
    ) -> None:
        pad = _bevestig(tmp_path, 1, ID_A, "2026-12-15")

        ruim_bevestigd_op(tmp_path, nu=_dag(2027, 4, 1))

        assert not pad.exists()

    def test_each_confirmation_follows_its_own_date(self, tmp_path: Path) -> None:
        oud = _bevestig(tmp_path, 1, ID_A, "2026-01-10")
        jong = _bevestig(tmp_path, 1, ID_B, "2026-05-10")

        ruim_bevestigd_op(tmp_path, nu=_dag(2026, 7, 15))

        assert (oud.exists(), jong.exists()) == (False, True)

    def test_the_count_per_tenant_is_returned(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, 1, ID_A, "2025-01-10")
        _bevestig(tmp_path, 1, ID_B, "2025-02-10")
        _bevestig(tmp_path, 2, ID_A, "2025-01-10")
        _bevestig(tmp_path, 3, ID_A, "2026-09-01")

        assert ruim_bevestigd_op(tmp_path, nu=_dag(2026, 10, 17)) == {1: 2, 2: 1}

    def test_another_tenant_with_a_confirmation_inside_the_term_is_left_alone(
        self, tmp_path: Path
    ) -> None:
        weg = _bevestig(tmp_path, 1, ID_A, "2025-01-10")
        blijft = _bevestig(tmp_path, 2, ID_A, "2026-09-01")

        ruim_bevestigd_op(tmp_path, nu=_dag(2026, 10, 17))

        assert (weg.exists(), blijft.exists()) == (False, True)


class TestWatNooitWegMag:
    def test_a_confirmation_without_a_readable_date_stays(self, tmp_path: Path) -> None:
        pad = _bevestig(tmp_path, 1, ID_A, "geen datum")

        ruim_bevestigd_op(tmp_path, nu=_dag(2030, 1, 1))

        assert pad.exists()

    def test_a_confirmation_without_a_date_field_stays(self, tmp_path: Path) -> None:
        map_ = tmp_path / "1"
        map_.mkdir()
        pad = map_ / f"{ID_A}.bevestigd.json"
        pad.write_text(json.dumps({"velden": {"totaal": "1.00"}}), encoding="utf-8")

        ruim_bevestigd_op(tmp_path, nu=_dag(2030, 1, 1))

        assert pad.exists()

    def test_a_damaged_confirmation_stays(self, tmp_path: Path) -> None:
        map_ = tmp_path / "1"
        map_.mkdir()
        pad = map_ / f"{ID_A}.bevestigd.json"
        pad.write_text("{kapot", encoding="utf-8")

        ruim_bevestigd_op(tmp_path, nu=_dag(2030, 1, 1))

        assert pad.exists()

    def test_the_bon_and_its_files_are_not_touched(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, 1, ID_A, "2020-01-01")
        bon = tmp_path / "1" / ID_A
        bon.write_bytes(b"x")
        meta = tmp_path / "1" / f"{ID_A}.meta.json"
        meta.write_bytes(b"{}")
        resultaat = tmp_path / "1" / f"{ID_A}.resultaat.json"
        resultaat.write_bytes(b"{}")

        ruim_bevestigd_op(tmp_path, nu=_dag(2030, 1, 1))

        assert (bon.exists(), meta.exists(), resultaat.exists()) == (True, True, True)

    def test_a_file_with_another_name_is_not_touched(self, tmp_path: Path) -> None:
        _bevestig(tmp_path, 1, ID_A, "2020-01-01")
        vreemd = tmp_path / "1" / "notities.bevestigd.json"
        vreemd.write_text(json.dumps({"velden": {"datum": "2020-01-01"}}), encoding="utf-8")
        kort = tmp_path / "1" / f"{'d' * 31}.pdf.bevestigd.json"
        kort.write_text(json.dumps({"velden": {"datum": "2020-01-01"}}), encoding="utf-8")

        ruim_bevestigd_op(tmp_path, nu=_dag(2030, 1, 1))

        assert (vreemd.exists(), kort.exists()) == (True, True)

    def test_a_folder_that_is_not_a_tenant_number_is_not_touched(self, tmp_path: Path) -> None:
        pad = _bevestig(tmp_path, 1, ID_A, "2020-01-01")
        pad_vreemd = tmp_path / "bijlagen"
        pad_vreemd.mkdir()
        vreemd = pad_vreemd / pad.name
        vreemd.write_text(pad.read_text(encoding="utf-8"), encoding="utf-8")

        ruim_bevestigd_op(tmp_path, nu=_dag(2030, 1, 1))

        assert vreemd.exists()

    def test_a_missing_upload_folder_is_no_error(self, tmp_path: Path) -> None:
        assert ruim_bevestigd_op(tmp_path / "bestaat-niet", nu=_dag(2030, 1, 1)) == {}

    def test_a_symlinked_confirmation_is_not_followed(self, tmp_path: Path) -> None:
        buiten = tmp_path / "buiten.json"
        buiten.write_text(json.dumps({"velden": {"datum": "2020-01-01"}}), encoding="utf-8")
        map_ = tmp_path / "uploads" / "1"
        map_.mkdir(parents=True)
        schakel = map_ / f"{ID_A}.bevestigd.json"
        try:
            os.symlink(buiten, schakel)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks zijn hier niet toegestaan")

        ruim_bevestigd_op(tmp_path / "uploads", nu=_dag(2030, 1, 1))

        assert buiten.exists()


class TestEenFoutStoptDeRestNiet:
    def test_an_unreadable_tenant_folder_does_not_stop_the_next_tenant(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        kapot = _bevestig(tmp_path, 1, ID_A, "2020-01-01")
        weg = _bevestig(tmp_path, 2, ID_A, "2020-01-01")
        echte_scandir = os.scandir

        def _scandir(pad: object) -> object:
            if str(pad).endswith(f"{os.sep}1"):
                raise PermissionError("geen toegang")
            return echte_scandir(pad)  # type: ignore[call-overload]

        monkeypatch.setattr(os, "scandir", _scandir)

        resultaat = ruim_bevestigd_op(tmp_path, nu=_dag(2030, 1, 1))

        assert (resultaat, kapot.exists(), weg.exists()) == ({2: 1}, True, False)


def _bevestig_op(root: Path, tenant: int, bestand_id: str, datum: str, bevestigd_op: str) -> Path:
    pad = _bevestig(root, tenant, bestand_id, datum)
    record = json.loads(pad.read_text(encoding="utf-8"))
    record["bevestigd_op"] = bevestigd_op
    pad.write_text(json.dumps(record), encoding="utf-8")
    return pad


class TestDeBondatumIsInvoerVanEenGebruiker:
    """Security-review: de medewerker kiest de bondatum; die mag de termijn niet naar nul of oneindig sturen,
    en een extreme datum mag de opruiming van andere tenants niet blokkeren."""

    def test_the_year_9999_does_not_crash_the_term(self) -> None:
        assert bewaar_tot("9999-10-01") is not None

    def test_a_confirmation_with_the_year_9999_does_not_stop_the_other_tenants(
        self, tmp_path: Path
    ) -> None:
        _bevestig(tmp_path, 1, ID_A, "9999-10-01")
        weg = _bevestig(tmp_path, 2, ID_A, "2020-01-01")

        resultaat = ruim_bevestigd_op(tmp_path, nu=_dag(2030, 1, 1))

        assert (resultaat, weg.exists()) == ({2: 1}, False)

    def test_a_confirmation_with_a_date_long_ago_stays_30_days_after_confirming(
        self, tmp_path: Path
    ) -> None:
        pad = _bevestig_op(tmp_path, 1, ID_A, "2020-01-01", "2030-01-01T10:00:00+00:00")

        ruim_bevestigd_op(tmp_path, nu=_dag(2030, 1, 31))

        assert pad.exists()

    def test_a_confirmation_with_a_date_long_ago_goes_the_day_after_those_30_days(
        self, tmp_path: Path
    ) -> None:
        pad = _bevestig_op(tmp_path, 1, ID_A, "2020-01-01", "2030-01-01T10:00:00+00:00")

        ruim_bevestigd_op(tmp_path, nu=_dag(2030, 2, 1))

        assert not pad.exists()

    def test_a_confirmation_with_a_date_far_in_the_future_goes_after_10_years(
        self, tmp_path: Path
    ) -> None:
        pad = _bevestig_op(tmp_path, 1, ID_A, "9998-12-31", "2026-10-17T10:00:00+00:00")

        ruim_bevestigd_op(tmp_path, nu=_dag(2036, 10, 18))

        assert not pad.exists()

    def test_a_confirmation_with_a_date_far_in_the_future_stays_within_10_years(
        self, tmp_path: Path
    ) -> None:
        pad = _bevestig_op(tmp_path, 1, ID_A, "9998-12-31", "2026-10-17T10:00:00+00:00")

        ruim_bevestigd_op(tmp_path, nu=_dag(2036, 10, 17))

        assert pad.exists()

    def test_a_normal_confirmation_still_follows_the_quarter_rule(self, tmp_path: Path) -> None:
        pad = _bevestig_op(tmp_path, 1, ID_A, "2026-02-26", "2026-03-01T10:00:00+00:00")

        ruim_bevestigd_op(tmp_path, nu=_dag(2026, 6, 30))

        assert pad.exists()

    def test_a_normal_confirmation_goes_the_day_after_the_quarter_term(
        self, tmp_path: Path
    ) -> None:
        pad = _bevestig_op(tmp_path, 1, ID_A, "2026-02-26", "2026-03-01T10:00:00+00:00")

        ruim_bevestigd_op(tmp_path, nu=_dag(2026, 7, 1))

        assert not pad.exists()

    def test_an_unreadable_confirmation_moment_falls_back_on_the_date_alone(
        self, tmp_path: Path
    ) -> None:
        pad = _bevestig_op(tmp_path, 1, ID_A, "2026-02-26", "geen tijdstip")

        ruim_bevestigd_op(tmp_path, nu=_dag(2026, 7, 1))

        assert not pad.exists()

    def test_deeply_nested_json_does_not_stop_the_run(self, tmp_path: Path) -> None:
        map_ = tmp_path / "1"
        map_.mkdir()
        (map_ / f"{ID_A}.bevestigd.json").write_text("[" * 20000, encoding="utf-8")
        weg = _bevestig(tmp_path, 2, ID_A, "2020-01-01")

        resultaat = ruim_bevestigd_op(tmp_path, nu=_dag(2030, 1, 1))

        assert (resultaat, weg.exists()) == ({2: 1}, False)
