"""Acceptatie dag 4: het leesresultaat staat naast de bon (`<bestand_id>.resultaat.json`) en valt onder dezelfde
30 dagen als de bon en zijn metabestand (besluit Rakesh 2026-10-17; de regie bevestigde dat het leesresultaat
onder de 30 dagen van de bon valt).

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.core.als.bonlezer.opruimen import ruim_op

NU = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
ID_A = "a" * 32 + ".pdf"


def _maak(root: Path, tenant: int, naam: str, dagen_oud: float) -> Path:
    map_ = root / str(tenant)
    map_.mkdir(parents=True, exist_ok=True)
    pad = map_ / naam
    pad.write_bytes(b"x")
    tijd = (NU - timedelta(days=dagen_oud)).timestamp()
    os.utime(pad, (tijd, tijd))
    return pad


def _bon(root: Path, tenant: int, dagen_oud: float) -> None:
    _maak(root, tenant, ID_A, dagen_oud)
    _maak(root, tenant, f"{ID_A}.meta.json", dagen_oud)


class TestHetResultaatbestandGaatMetDeBonMee:
    def test_the_stored_result_of_a_bon_of_31_days_is_removed(self, tmp_path: Path) -> None:
        _bon(tmp_path, 1, 31)
        resultaat = _maak(tmp_path, 1, f"{ID_A}.resultaat.json", 31)

        ruim_op(tmp_path, nu=NU)

        assert not resultaat.exists()

    def test_the_stored_result_of_a_bon_of_29_days_stays(self, tmp_path: Path) -> None:
        _bon(tmp_path, 1, 29)
        resultaat = _maak(tmp_path, 1, f"{ID_A}.resultaat.json", 29)

        ruim_op(tmp_path, nu=NU)

        assert resultaat.exists()

    def test_a_leftover_temporary_result_file_is_removed_with_the_bon(self, tmp_path: Path) -> None:
        _bon(tmp_path, 1, 31)
        rest = _maak(tmp_path, 1, f"{ID_A}.resultaat.json.0123abcd.tmp", 31)

        ruim_op(tmp_path, nu=NU)

        assert not rest.exists()

    def test_the_stored_result_does_not_make_the_bon_count_double(self, tmp_path: Path) -> None:
        _bon(tmp_path, 1, 31)
        _maak(tmp_path, 1, f"{ID_A}.resultaat.json", 31)

        assert ruim_op(tmp_path, nu=NU) == {1: 1}

    def test_the_stored_result_of_another_tenant_stays(self, tmp_path: Path) -> None:
        _bon(tmp_path, 1, 31)
        _bon(tmp_path, 2, 5)
        ander = _maak(tmp_path, 2, f"{ID_A}.resultaat.json", 5)

        ruim_op(tmp_path, nu=NU)

        assert ander.exists()

    def test_the_stored_result_is_removed_with_the_bon_even_when_it_is_younger(
        self, tmp_path: Path
    ) -> None:
        """Het resultaat wordt pas bij het eerste ophalen vastgelegd (jonger dan de bon): de bon bepaalt de termijn."""
        _bon(tmp_path, 1, 31)
        resultaat = _maak(tmp_path, 1, f"{ID_A}.resultaat.json", 10)

        ruim_op(tmp_path, nu=NU)

        assert not resultaat.exists()
