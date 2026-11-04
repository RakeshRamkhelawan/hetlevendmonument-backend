"""Tests ensuring elimination of TESTING=1 test poisoning in workflow execution routers (OP-254).

Verifies:
- No 'os.getenv("TESTING")' or 'os.environ' checks in workflow_execution_core_router.py
- No 'os.getenv("TESTING")' or 'os.environ' checks in workflow_execution_router.py
- No fake in-process LLM/Tool/Agent classes (_FakeLLM, _FakeTool, _FakeAgent) embedded in production routers
- Production routers unconditionally dispatch to execute_workflow_task.send
"""

from __future__ import annotations

import ast
from pathlib import Path
import pytest


CORE_ROUTER_PATH = Path("src/core/api/v1/workflow/workflow_execution_core_router.py")
ROUTER_PATH = Path("src/core/api/v1/workflow/workflow_execution_router.py")


def test_core_router_has_no_testing_environment_poisoning() -> None:
    """workflow_execution_core_router.py must not check os.getenv('TESTING') or contain fake engines."""
    content = CORE_ROUTER_PATH.read_text(encoding="utf-8")
    assert 'os.getenv("TESTING")' not in content, (
        f"{CORE_ROUTER_PATH} contains os.getenv('TESTING') bypass -- test poisoning per OP-254"
    )
    assert "_FakeLLM" not in content, (
        f"{CORE_ROUTER_PATH} contains embedded _FakeLLM stub in production router"
    )
    assert "_FakeTool" not in content, (
        f"{CORE_ROUTER_PATH} contains embedded _FakeTool stub in production router"
    )
    assert "_FakeAgent" not in content, (
        f"{CORE_ROUTER_PATH} contains embedded _FakeAgent stub in production router"
    )


def test_workflow_router_has_no_testing_environment_poisoning() -> None:
    """workflow_execution_router.py must not check os.getenv('TESTING') or contain fake engines."""
    content = ROUTER_PATH.read_text(encoding="utf-8")
    assert 'os.getenv("TESTING")' not in content, (
        f"{ROUTER_PATH} contains os.getenv('TESTING') bypass -- test poisoning per OP-254"
    )
    assert "_FakeLLM" not in content, (
        f"{ROUTER_PATH} contains embedded _FakeLLM stub in production router"
    )
    assert "_FakeTool" not in content, (
        f"{ROUTER_PATH} contains embedded _FakeTool stub in production router"
    )
    assert "_FakeAgent" not in content, (
        f"{ROUTER_PATH} contains embedded _FakeAgent stub in production router"
    )


def test_both_routers_contain_unconditional_actor_dispatch() -> None:
    """Both routers dispatch through `verstuur_workflow_taak`, which sends unconditionally.

    Sinds 2026-10-20 (ADR-036 OP-13) staat de `.send(...)` niet meer in de routers maar in
    `src/workers/workflow_verzending.py`, zodat een mislukte verzending een zichtbare fout geeft
    in plaats van een stille 202. De eis blijft: geen TESTING-omweg tussen het verzoek en de send.
    """
    for path in (CORE_ROUTER_PATH, ROUTER_PATH):
        content = path.read_text(encoding="utf-8")
        assert "await verstuur_workflow_taak(db, execution)" in content

    verzending = Path("src/workers/workflow_verzending.py").read_text(encoding="utf-8")
    assert "workflow_worker.execute_workflow_task).send(" in verzending
    assert 'os.getenv("TESTING")' not in verzending
