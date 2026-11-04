"""De dagelijkse opruiming ruimt ook bevestigde velden op na hun eigen termijn (bonlezer dag 4, besluit Rakesh
2026-10-17, "optie 2": einde van het kwartaal van de bondatum plus 3 maanden).

De termijnregels staan in `tests/unit/bonlezer/test_opruimen_bevestigd.py`. Hier: de actor roept het aan, schrijft
per tenant EEN auditregel met alleen het AANTAL (geen bestandsnamen, geen cijfers van de bon), laat het
verwijderen van bonnen en van bevestigingen los van elkaar werken, en een falende auditregel draait niets terug.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.tasks import bonnen_opruimen

NU = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
ID_A = "a" * 32 + ".pdf"
ID_B = "b" * 32 + ".jpg"


def _bevestig(root: Path, tenant: int, bestand_id: str, datum: str) -> Path:
    map_ = root / str(tenant)
    map_.mkdir(parents=True, exist_ok=True)
    pad = map_ / f"{bestand_id}.bevestigd.json"
    pad.write_text(json.dumps({"velden": {"datum": datum, "totaal": "1.00"}}), encoding="utf-8")
    return pad


def _bon(root: Path, tenant: int, bestand_id: str, dagen_oud: float) -> Path:
    map_ = root / str(tenant)
    map_.mkdir(parents=True, exist_ok=True)
    pad = map_ / bestand_id
    pad.write_bytes(b"x")
    tijd = (NU - timedelta(days=dagen_oud)).timestamp()
    os.utime(pad, (tijd, tijd))
    return pad


@pytest.fixture
def audit(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    logger = AsyncMock()
    monkeypatch.setattr(bonnen_opruimen.AuditService, "log_action", logger)

    @asynccontextmanager
    async def _geen_tenantcontext(sessie: Any, tenant_id: int) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr(bonnen_opruimen, "adopt_tenant", _geen_tenantcontext)
    return logger


@asynccontextmanager
async def _fabriek() -> AsyncIterator[AsyncMock]:
    yield AsyncMock()


def _draai(root: Path) -> dict[int, int]:
    return asyncio.run(
        bonnen_opruimen.ruim_bonnen_op_async(sessie_fabriek=_fabriek, nu=NU, root=root)
    )


class TestDeBevestigingenWordenOpgeruimd:
    def test_a_confirmation_past_its_term_is_removed(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        pad = _bevestig(tmp_path, 1, ID_A, "2026-02-26")  # termijn tot en met 2026-06-30

        _draai(tmp_path)

        assert not pad.exists()

    def test_a_confirmation_inside_its_term_stays(self, tmp_path: Path, audit: AsyncMock) -> None:
        pad = _bevestig(tmp_path, 1, ID_A, "2026-09-01")  # termijn tot en met 2027-03-31

        _draai(tmp_path)

        assert pad.exists()

    def test_the_cleanup_of_bonnen_still_returns_only_the_bonnen(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        _bon(tmp_path, 1, ID_A, 40)
        _bevestig(tmp_path, 1, ID_B, "2025-01-01")

        assert _draai(tmp_path) == {1: 1}

    def test_a_confirmation_is_removed_without_any_bon_to_remove(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        pad = _bevestig(tmp_path, 1, ID_A, "2025-01-01")

        _draai(tmp_path)

        assert not pad.exists()

    def test_another_tenant_inside_its_term_is_left_alone(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        weg = _bevestig(tmp_path, 1, ID_A, "2025-01-01")
        blijft = _bevestig(tmp_path, 2, ID_A, "2026-09-01")

        _draai(tmp_path)

        assert (weg.exists(), blijft.exists()) == (False, True)


class TestDeAuditregelVoorBevestigingen:
    def test_one_audit_line_per_tenant_with_a_confirmation_removed(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        _bevestig(tmp_path, 1, ID_A, "2025-01-01")
        _bevestig(tmp_path, 2, ID_A, "2025-01-01")
        _bevestig(tmp_path, 3, ID_A, "2026-09-01")

        _draai(tmp_path)

        assert sorted(c.kwargs["tenant_id"] for c in audit.await_args_list) == [1, 2]

    def test_the_audit_line_has_the_count_only(self, tmp_path: Path, audit: AsyncMock) -> None:
        _bevestig(tmp_path, 4, ID_A, "2025-01-01")
        _bevestig(tmp_path, 4, ID_B, "2025-02-01")

        _draai(tmp_path)

        kwargs = audit.await_args.kwargs  # type: ignore[union-attr]
        assert (kwargs["action"], kwargs["details"], kwargs["endpoint"]) == (
            "bevestigde_bonnen_opgeruimd",
            {"bevestigingen_verwijderd": 2},
            "worker:ruim_bonnen_op",
        )

    def test_the_audit_line_has_no_file_names_or_amounts(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        _bevestig(tmp_path, 4, ID_A, "2025-01-01")

        _draai(tmp_path)

        tekst = str(audit.await_args.kwargs)  # type: ignore[union-attr]
        assert ID_A not in tekst and "1.00" not in tekst

    def test_no_audit_line_when_nothing_was_removed(self, tmp_path: Path, audit: AsyncMock) -> None:
        _bevestig(tmp_path, 1, ID_A, "2026-09-01")

        _draai(tmp_path)

        assert audit.await_count == 0

    def test_bonnen_and_confirmations_each_get_their_own_line(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        _bon(tmp_path, 1, ID_A, 40)
        _bevestig(tmp_path, 1, ID_B, "2025-01-01")

        _draai(tmp_path)

        assert sorted(c.kwargs["action"] for c in audit.await_args_list) == [
            "bevestigde_bonnen_opgeruimd",
            "bonnen_opgeruimd",
        ]

    def test_a_failing_audit_line_does_not_undo_the_removal(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        pad = _bevestig(tmp_path, 1, ID_A, "2025-01-01")
        audit.side_effect = RuntimeError("audit stuk")

        _draai(tmp_path)

        assert not pad.exists()
