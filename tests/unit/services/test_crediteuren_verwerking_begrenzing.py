"""De start van de crediteurenagent na een upload is begrensd (crediteuren dag 2, Gate 2).

Een wachtende verwerking bezet bij elke poll een thread. Zonder grens kan een stroom uploads de threadpool van de API vullen. Een start
die er niet meer bij past wordt niet vergeten: de stand (`GET /api/v1/payables/inlezen/{id}`) start hem later alsnog.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from src.core.services import crediteuren_verwerking as verwerking


@pytest_asyncio.fixture
async def wachtend(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[asyncio.Event, None]:
    """Elke verwerking wacht tot de test hem loslaat; zo blijven ze `bezig` zolang de test telt."""
    vrij = asyncio.Event()

    async def _wacht(tenant_id: int, bestand_id: str, user_id: int) -> dict[str, object]:
        await vrij.wait()
        return {"uitkomst": "vastgelegd"}

    monkeypatch.setattr(verwerking, "verwerk_zodra_gelezen", _wacht)
    verwerking._BEZIG.clear()
    yield vrij
    vrij.set()
    await asyncio.sleep(0)
    verwerking._BEZIG.clear()


@pytest.mark.asyncio
async def test_a_tenant_can_have_five_waiting_processes(wachtend: asyncio.Event) -> None:
    for i in range(7):
        verwerking.start_verwerking(1, f"{i:032x}.pdf", 1)

    assert sum(1 for tenant, _ in verwerking._BEZIG if tenant == 1) == verwerking.MAX_PER_TENANT


@pytest.mark.asyncio
async def test_another_tenant_is_not_blocked_by_a_full_tenant(wachtend: asyncio.Event) -> None:
    for i in range(7):
        verwerking.start_verwerking(1, f"{i:032x}.pdf", 1)

    verwerking.start_verwerking(2, "a" * 32 + ".pdf", 1)

    assert (2, "a" * 32 + ".pdf") in verwerking._BEZIG


@pytest.mark.asyncio
async def test_the_whole_process_has_a_limit_too(
    wachtend: asyncio.Event, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(verwerking, "MAX_TOTAAL", 3)

    for tenant in range(1, 7):
        verwerking.start_verwerking(tenant, "b" * 32 + ".pdf", 1)

    assert len(verwerking._BEZIG) == 3


@pytest.mark.asyncio
async def test_the_same_upload_is_started_once(wachtend: asyncio.Event) -> None:
    verwerking.start_verwerking(1, "c" * 32 + ".pdf", 1)
    verwerking.start_verwerking(1, "c" * 32 + ".pdf", 1)

    assert len(verwerking._BEZIG) == 1


@pytest.mark.asyncio
async def test_a_finished_process_makes_room_again(wachtend: asyncio.Event) -> None:
    for i in range(5):
        verwerking.start_verwerking(1, f"{i:032x}.pdf", 1)
    wachtend.set()
    for _ in range(5):
        await asyncio.sleep(0)

    verwerking.start_verwerking(1, "d" * 32 + ".pdf", 1)

    assert (1, "d" * 32 + ".pdf") in verwerking._BEZIG
