import asyncio
import contextlib
from collections.abc import AsyncIterator, Iterator

import pytest

"""Fixtures voor de tool_broker-unittests.

`TestActEndToEnd` roept `BaseSpecialistAgent.act()` rechtstreeks aan. Sinds BE-AGT-041,
BE-AGT-042 en ADR-036 OP-163 raakt dat pad drie governance-lagen die een databaseverbinding
openen, dus dezelfde stubs als in tests/unit/als en tests/unit/agents gelden hier ook.
"""

from tests.fixtures.agent_governance import (  # noqa: F401
    council_gate,
    hitl_ticket_repository,
    prana_guard,
)


@pytest.fixture(autouse=True)
def _deterministic_pseudonymisation_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin de pseudonimiseringssleutel en ruim hem op (ADR-036 OP-27).

    `redaction` cachet de sleutel in een module-globale. Zonder deze fixture laat een test die
    een eigen sleutel zet die achter voor elke latere test in dezelfde xdist-worker -- precies
    het patroon dat OP-20 blootlegde. Resetten voor EN na, niet alleen voor.
    """
    from src.core.tool_broker import redaction

    monkeypatch.setenv(redaction.KEY_ENV_VAR, "test-pseudonymisation-key-" + "0" * 32)
    redaction.reset_key_cache()
    yield
    redaction.reset_key_cache()


@pytest.fixture(params=[False, True], ids=["schoon", "vreemde_taak"])
async def audittaken_vooraf(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    """Zet (bij `vreemde_taak`) een onafgemaakte taak van een andere test in `_AUDIT_TASKS`.

    Gate 2 F7: `_AUDIT_TASKS` is een verzameling op moduleniveau. In een volledige parallelle ronde
    kan een andere test op dezelfde worker er een taak in achterlaten; een test die de hele
    verzameling telt, valt daar dan om. Deze fixture maakt dat reproduceerbaar.
    """
    from src.core.tool_broker import service as service_module

    if not request.param:
        yield
        return
    vreemd = asyncio.create_task(asyncio.Event().wait(), name="vreemde-audittaak")
    service_module._AUDIT_TASKS.add(vreemd)
    try:
        yield
    finally:
        vreemd.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await vreemd
        service_module._AUDIT_TASKS.discard(vreemd)
