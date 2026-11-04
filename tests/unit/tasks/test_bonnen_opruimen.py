"""De dagelijkse opruiming van geuploade bonnen: de actor `ruim_bonnen_op` (bonlezer dag 4).

De kern (`src/core/als/bonlezer/opruimen.py`) wordt in `tests/unit/bonlezer/test_opruimen.py` getoetst. Hier:
de actor roept hem aan met de uploadmap en de klok, schrijft per tenant EEN auditregel met alleen het aantal,
laat een falende auditregel de opruiming niet terugdraaien, en heet zoals de scheduler hem aanroept.

Besluit Rakesh 2026-10-17: "30 dagen bewaren en zijn daarmee lezer".

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable
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


class TestDeOpruiming:
    def test_an_old_bon_is_removed(self, tmp_path: Path, audit: AsyncMock) -> None:
        bon = _bon(tmp_path, 1, ID_A, 31)

        _draai(tmp_path)

        assert not bon.exists()

    def test_a_young_bon_stays(self, tmp_path: Path, audit: AsyncMock) -> None:
        bon = _bon(tmp_path, 1, ID_A, 29)

        _draai(tmp_path)

        assert bon.exists()

    def test_the_count_per_tenant_is_returned(self, tmp_path: Path, audit: AsyncMock) -> None:
        _bon(tmp_path, 1, ID_A, 40)
        _bon(tmp_path, 1, ID_B, 40)
        _bon(tmp_path, 2, ID_A, 40)

        assert _draai(tmp_path) == {1: 2, 2: 1}

    def test_the_real_clock_is_used_without_a_given_time(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        bon = _bon(tmp_path, 1, ID_A, 0)
        os.utime(bon, (0, 0))  # 1970: ouder dan 30 dagen volgens de echte klok

        asyncio.run(bonnen_opruimen.ruim_bonnen_op_async(sessie_fabriek=_fabriek, root=tmp_path))

        assert not bon.exists()

    def test_the_upload_folder_comes_from_the_environment(
        self, tmp_path: Path, audit: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bon = _bon(tmp_path, 1, ID_A, 40)
        monkeypatch.setenv("BONLEZER_UPLOAD_ROOT", str(tmp_path))

        asyncio.run(bonnen_opruimen.ruim_bonnen_op_async(sessie_fabriek=_fabriek, nu=NU))

        assert not bon.exists()


class TestDeAuditregel:
    def test_one_audit_line_per_tenant_with_something_removed(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        _bon(tmp_path, 1, ID_A, 40)
        _bon(tmp_path, 2, ID_A, 40)
        _bon(tmp_path, 3, ID_A, 2)

        _draai(tmp_path)

        assert sorted(c.kwargs["tenant_id"] for c in audit.await_args_list) == [1, 2]

    def test_no_audit_line_when_nothing_was_removed(self, tmp_path: Path, audit: AsyncMock) -> None:
        _bon(tmp_path, 1, ID_A, 2)

        _draai(tmp_path)

        assert audit.await_count == 0

    def test_the_audit_line_has_the_count_and_the_retention(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        _bon(tmp_path, 4, ID_A, 40)
        _bon(tmp_path, 4, ID_B, 41)

        _draai(tmp_path)

        kwargs = audit.await_args.kwargs  # type: ignore[union-attr]
        assert kwargs["details"] == {"bonnen_verwijderd": 2, "bewaardagen": 30}

    def test_the_audit_line_names_the_action_and_the_worker(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        _bon(tmp_path, 4, ID_A, 40)

        _draai(tmp_path)

        kwargs = audit.await_args.kwargs  # type: ignore[union-attr]
        assert (kwargs["action"], kwargs["endpoint"]) == (
            "bonnen_opgeruimd",
            "worker:ruim_bonnen_op",
        )

    def test_the_audit_line_has_no_file_names(self, tmp_path: Path, audit: AsyncMock) -> None:
        _bon(tmp_path, 4, ID_A, 40)

        _draai(tmp_path)

        assert ID_A not in str(audit.await_args.kwargs)  # type: ignore[union-attr]

    def test_a_failing_audit_line_does_not_undo_the_cleanup(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        bon = _bon(tmp_path, 1, ID_A, 40)
        audit.side_effect = RuntimeError("audit stuk")

        resultaat = _draai(tmp_path)

        assert (bon.exists(), resultaat) == (False, {1: 1})

    def test_a_failing_audit_line_does_not_stop_the_next_tenant(
        self, tmp_path: Path, audit: AsyncMock
    ) -> None:
        _bon(tmp_path, 1, ID_A, 40)
        _bon(tmp_path, 2, ID_A, 40)
        audit.side_effect = [RuntimeError("audit stuk"), None]

        _draai(tmp_path)

        assert audit.await_count == 2


class TestDeActor:
    def test_the_actor_has_the_name_the_scheduler_calls(self) -> None:
        assert bonnen_opruimen.ruim_bonnen_op.actor_name == "ruim_bonnen_op"

    def test_the_actor_does_not_retry(self) -> None:
        # De volgende dagrun pakt wat blijft liggen; een tweede poging is niet nodig.
        assert bonnen_opruimen.ruim_bonnen_op.options["max_retries"] == 0

    def test_the_actor_hands_the_session_factory_to_the_core(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ontvangen: dict[str, Any] = {}

        async def _kern(
            sessie_fabriek: Any = None, nu: Any = None, root: Any = None
        ) -> dict[int, int]:
            ontvangen["fabriek"] = sessie_fabriek
            return {}

        def _draai_in_lus(taak: Callable[[Any], Any]) -> None:
            asyncio.run(taak("de-fabriek"))

        monkeypatch.setattr(bonnen_opruimen, "ruim_bonnen_op_async", _kern)
        monkeypatch.setattr(bonnen_opruimen, "draai_in_eigen_loop", _draai_in_lus)

        bonnen_opruimen.ruim_bonnen_op.fn()

        assert ontvangen == {"fabriek": "de-fabriek"}
