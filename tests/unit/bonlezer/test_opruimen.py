"""Bonlezer dag 4: de opruiming van geuploade bonnen na 30 dagen.

Besluit Rakesh 2026-10-17: "30 dagen bewaren en zijn daarmee lezer". Het akkoord (interlock 1) geldt voor
PRECIES dit: de geuploade bon en zijn metabestand na 30 dagen verwijderen. Daarom toetsen deze tests vooral
wat er NIET mag verdwijnen: een bon van 29 dagen, de bevestigde velden, bestanden met een andere naam,
een map die geen tenantnummer is, en alles wat via een symlink buiten de uploadmap zou wijzen.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.core.als.bonlezer.opruimen import BEWAARDAGEN, ruim_op

NU = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
ID_A = "a" * 32 + ".pdf"
ID_B = "b" * 32 + ".jpg"
ID_C = "c" * 32 + ".png"


def _maak(root: Path, tenant: int | str, naam: str, dagen_oud: float, inhoud: bytes = b"x") -> Path:
    map_ = root / str(tenant) if str(tenant) else root
    map_.mkdir(parents=True, exist_ok=True)
    pad = map_ / naam
    pad.write_bytes(inhoud)
    tijd = (NU - timedelta(days=dagen_oud)).timestamp()
    os.utime(pad, (tijd, tijd))
    return pad


def _bon(root: Path, tenant: int, bestand_id: str, dagen_oud: float) -> tuple[Path, Path]:
    return (
        _maak(root, tenant, bestand_id, dagen_oud),
        _maak(root, tenant, f"{bestand_id}.meta.json", dagen_oud),
    )


class TestWatWegMag:
    def test_a_bon_of_31_days_is_removed(self, tmp_path: Path) -> None:
        bon, _ = _bon(tmp_path, 1, ID_A, 31)

        ruim_op(tmp_path, nu=NU)

        assert not bon.exists()

    def test_the_metadata_of_a_bon_of_31_days_is_removed(self, tmp_path: Path) -> None:
        _, meta = _bon(tmp_path, 1, ID_A, 31)

        ruim_op(tmp_path, nu=NU)

        assert not meta.exists()

    def test_a_leftover_temporary_metadata_file_of_31_days_is_removed(self, tmp_path: Path) -> None:
        tijdelijk = _maak(tmp_path, 1, f"{ID_A}.meta.json.1a2b3c4d.tmp", 31)

        ruim_op(tmp_path, nu=NU)

        assert not tijdelijk.exists()

    def test_a_bon_without_metadata_of_31_days_is_removed(self, tmp_path: Path) -> None:
        bon = _maak(tmp_path, 1, ID_A, 31)

        ruim_op(tmp_path, nu=NU)

        assert not bon.exists()

    def test_metadata_without_a_bon_of_31_days_is_removed(self, tmp_path: Path) -> None:
        meta = _maak(tmp_path, 1, f"{ID_A}.meta.json", 31)

        ruim_op(tmp_path, nu=NU)

        assert not meta.exists()

    def test_the_bon_is_removed_even_when_its_metadata_was_touched_recently(
        self, tmp_path: Path
    ) -> None:
        """De status-aanroep schrijft het metabestand opnieuw; de leeftijd telt vanaf de upload."""
        bon = _maak(tmp_path, 1, ID_A, 31)
        meta = _maak(tmp_path, 1, f"{ID_A}.meta.json", 1)

        ruim_op(tmp_path, nu=NU)

        assert (bon.exists(), meta.exists()) == (False, False)

    def test_every_extension_the_upload_accepts_is_removed(self, tmp_path: Path) -> None:
        extensies = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")
        paden = [
            _maak(tmp_path, 1, f"{teken}" * 32 + ext, 40)
            for teken, ext in zip("123456", extensies, strict=True)
        ]

        ruim_op(tmp_path, nu=NU)

        assert [p.exists() for p in paden] == [False] * 6


class TestWatBlijft:
    def test_a_bon_of_29_days_stays(self, tmp_path: Path) -> None:
        bon, meta = _bon(tmp_path, 1, ID_A, 29)

        ruim_op(tmp_path, nu=NU)

        assert (bon.exists(), meta.exists()) == (True, True)

    def test_the_retention_is_30_days_as_decided_by_rakesh(self) -> None:
        """Besluit Rakesh 2026-10-17: "30 dagen bewaren". Een andere waarde is een ander besluit."""
        assert BEWAARDAGEN == 30

    def test_a_bon_of_exactly_30_days_stays(self, tmp_path: Path) -> None:
        bon, _ = _bon(tmp_path, 1, ID_A, 30)

        ruim_op(tmp_path, nu=NU)

        assert bon.exists()

    def test_a_bon_of_30_days_and_a_minute_is_removed(self, tmp_path: Path) -> None:
        bon, _ = _bon(tmp_path, 1, ID_A, 30 + 1 / 1440)

        ruim_op(tmp_path, nu=NU)

        assert not bon.exists()

    def test_the_confirmed_fields_stay_when_the_bon_is_removed(self, tmp_path: Path) -> None:
        _bon(tmp_path, 1, ID_A, 40)
        bevestigd = _maak(tmp_path, 1, f"{ID_A}.bevestigd.json", 40, b'{"velden": {}}')

        ruim_op(tmp_path, nu=NU)

        assert bevestigd.read_bytes() == b'{"velden": {}}'

    def test_files_with_another_name_stay(self, tmp_path: Path) -> None:
        andere = [
            _maak(tmp_path, 1, "notities.txt", 400),
            _maak(tmp_path, 1, "bon.pdf", 400),
            _maak(tmp_path, 1, "A" * 32 + ".pdf", 400),
            _maak(tmp_path, 1, "a" * 32 + ".exe", 400),
            _maak(tmp_path, 1, "a" * 31 + ".pdf", 400),
            _maak(tmp_path, 1, f"{ID_A}.bak", 400),
            _maak(tmp_path, 1, f"{ID_A}.bevestigd.json.1a2b3c4d.tmp", 400),
        ]

        ruim_op(tmp_path, nu=NU)

        assert [p.exists() for p in andere] == [True] * 7

    def test_a_folder_that_is_not_a_tenant_number_is_left_alone(self, tmp_path: Path) -> None:
        paden = [
            _maak(tmp_path, "notities", ID_A, 400),
            _maak(tmp_path, "0", ID_A, 400),
            _maak(tmp_path, "-1", ID_A, 400),
            _maak(tmp_path, "01x", ID_A, 400),
        ]

        ruim_op(tmp_path, nu=NU)

        assert [p.exists() for p in paden] == [True] * 4

    def test_a_loose_file_in_the_upload_folder_is_left_alone(self, tmp_path: Path) -> None:
        los = _maak(tmp_path, "", "kaart.json", 400)

        ruim_op(tmp_path, nu=NU)

        assert los.exists()

    def test_a_folder_with_a_bon_name_is_left_alone(self, tmp_path: Path) -> None:
        map_ = tmp_path / "1" / ID_A
        map_.mkdir(parents=True)
        (map_ / "x.txt").write_bytes(b"x")

        ruim_op(tmp_path, nu=NU)

        assert (map_ / "x.txt").exists()

    def test_a_missing_upload_folder_is_not_an_error(self, tmp_path: Path) -> None:
        assert ruim_op(tmp_path / "bestaat-niet", nu=NU) == {}


class TestPerTenant:
    def test_the_young_bonnen_of_other_tenants_stay_when_one_tenant_is_cleaned(
        self, tmp_path: Path
    ) -> None:
        oud, _ = _bon(tmp_path, 1, ID_A, 40)
        jong, _ = _bon(tmp_path, 2, ID_B, 3)

        ruim_op(tmp_path, nu=NU)

        assert (oud.exists(), jong.exists()) == (False, True)

    def test_an_old_bon_of_another_tenant_is_removed_too(self, tmp_path: Path) -> None:
        oud, _ = _bon(tmp_path, 2, ID_B, 40)

        ruim_op(tmp_path, nu=NU)

        assert not oud.exists()

    def test_the_same_bon_name_in_two_tenants_is_judged_per_tenant(self, tmp_path: Path) -> None:
        oud, _ = _bon(tmp_path, 1, ID_A, 40)
        jong, _ = _bon(tmp_path, 2, ID_A, 3)

        ruim_op(tmp_path, nu=NU)

        assert (oud.exists(), jong.exists()) == (False, True)

    def test_the_count_per_tenant_is_returned_in_bonnen(self, tmp_path: Path) -> None:
        _bon(tmp_path, 1, ID_A, 40)
        _bon(tmp_path, 1, ID_B, 41)
        _bon(tmp_path, 1, ID_C, 2)
        _bon(tmp_path, 7, ID_A, 50)

        assert ruim_op(tmp_path, nu=NU) == {1: 2, 7: 1}

    def test_a_tenant_without_anything_to_remove_is_not_reported(self, tmp_path: Path) -> None:
        _bon(tmp_path, 1, ID_A, 2)

        assert ruim_op(tmp_path, nu=NU) == {}

    def test_a_second_run_removes_nothing_more(self, tmp_path: Path) -> None:
        _bon(tmp_path, 1, ID_A, 40)
        ruim_op(tmp_path, nu=NU)

        assert ruim_op(tmp_path, nu=NU) == {}


class TestVeiligheid:
    def test_a_symlinked_bon_is_not_followed(self, tmp_path: Path) -> None:
        buiten = tmp_path / "buiten"
        buiten.mkdir()
        doel = buiten / "belangrijk.txt"
        doel.write_bytes(b"niet weghalen")
        os.utime(doel, (0, 0))
        map_ = tmp_path / "uploads" / "1"
        map_.mkdir(parents=True)
        try:
            os.symlink(doel, map_ / ID_A)
        except (OSError, NotImplementedError):
            pytest.skip("dit besturingssysteem staat hier geen symlinks toe")
        # De koppeling zelf is vers gemaakt: met `nu` ver in de toekomst zou hij "oud" zijn als hij
        # als gewoon bestand telde.
        veel_later = datetime.now(timezone.utc) + timedelta(days=90)

        ruim_op(tmp_path / "uploads", nu=veel_later)

        assert ((map_ / ID_A).is_symlink(), doel.read_bytes()) == (True, b"niet weghalen")

    def test_a_symlinked_tenant_folder_is_not_followed(self, tmp_path: Path) -> None:
        buiten = tmp_path / "buiten"
        buiten.mkdir()
        _maak(buiten, "", ID_A, 400)
        uploads = tmp_path / "uploads"
        uploads.mkdir()
        try:
            os.symlink(buiten, uploads / "1", target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("dit besturingssysteem staat hier geen symlinks toe")

        ruim_op(uploads, nu=NU)

        assert (buiten / ID_A).exists()

    def test_nothing_outside_the_upload_folder_is_touched(self, tmp_path: Path) -> None:
        uploads = tmp_path / "uploads"
        _bon(uploads, 1, ID_A, 40)
        ernaast = _maak(tmp_path, "andere-map", ID_A, 400)

        ruim_op(uploads, nu=NU)

        assert ernaast.exists()

    def test_a_file_that_cannot_be_removed_does_not_stop_the_rest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        eerste, _ = _bon(tmp_path, 1, ID_A, 40)
        tweede, _ = _bon(tmp_path, 1, ID_B, 40)
        echte_unlink = os.unlink

        def kapot(pad: str | os.PathLike[str], *args: object, **kwargs: object) -> None:
            if Path(pad) == eerste:
                raise PermissionError("geen rechten")
            echte_unlink(pad, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(os, "unlink", kapot)

        ruim_op(tmp_path, nu=NU)

        assert (eerste.exists(), tweede.exists()) == (True, False)

    def test_the_log_has_the_count_and_no_file_name(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _bon(tmp_path, 3, ID_A, 40)
        _bon(
            tmp_path, 3, ID_B, 2
        )  # blijft staan: een naam in het log zou dus een bestaand bestand zijn
        caplog.set_level(logging.INFO)

        ruim_op(tmp_path, nu=NU)

        assert "tenant=3" in caplog.text and "bonnen=1" in caplog.text
        assert ID_A not in caplog.text and ID_B not in caplog.text


class TestEenFoutStoptDeRestNiet:
    """Security- en code-review dag 4: een tenantmap die niet te lezen is mag de andere tenants niet blokkeren."""

    def test_an_unreadable_tenant_folder_does_not_stop_the_next_tenant(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        kapot, _ = _bon(tmp_path, 1, ID_A, 40)
        bon_b, _ = _bon(tmp_path, 2, ID_B, 40)
        echte_scandir = os.scandir

        def _scandir(pad: object) -> object:
            if str(pad).endswith(f"{os.sep}1"):
                raise PermissionError("geen toegang")
            return echte_scandir(pad)  # type: ignore[call-overload]

        monkeypatch.setattr(os, "scandir", _scandir)

        resultaat = ruim_op(tmp_path, nu=NU)

        assert (resultaat, kapot.exists(), bon_b.exists()) == ({2: 1}, True, False)

    def test_a_file_that_vanishes_during_the_run_does_not_stop_the_tenant(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _bon(tmp_path, 1, ID_A, 40)
        bon_b, _ = _bon(tmp_path, 1, ID_B, 40)
        echte_stat = os.DirEntry.stat

        def _stat(self: os.DirEntry[str], *, follow_symlinks: bool = True) -> os.stat_result:
            if self.name == ID_A:
                raise FileNotFoundError(self.name)
            return echte_stat(self, follow_symlinks=follow_symlinks)

        monkeypatch.setattr(os.DirEntry, "stat", _stat, raising=False)

        ruim_op(tmp_path, nu=NU)

        assert not bon_b.exists()

    def test_the_failure_is_logged_without_a_file_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _bon(tmp_path, 1, ID_A, 40)
        echte_scandir = os.scandir

        def _scandir(pad: object) -> object:
            if str(pad).endswith(f"{os.sep}1"):
                raise PermissionError("geheim-pad")
            return echte_scandir(pad)  # type: ignore[call-overload]

        monkeypatch.setattr(os, "scandir", _scandir)

        with caplog.at_level(logging.WARNING):
            ruim_op(tmp_path, nu=NU)

        assert "PermissionError" in caplog.text and "geheim-pad" not in caplog.text
