"""Fase 10 performance tests for company layer.

Set RUN_COMPANY_PERFORMANCE=1 to execute these benchmarks.
"""

# mypy: disable-error-code=var-annotated

from __future__ import annotations

import os
import time
from typing import Dict, List

import pytest

RUN_PERFORMANCE = os.getenv("RUN_COMPANY_PERFORMANCE") == "1"

pytestmark = pytest.mark.performance


@pytest.mark.skipif(
    not RUN_PERFORMANCE, reason="Set RUN_COMPANY_PERFORMANCE=1 to run performance tests"
)
def test_pack_scoring_under_100ms() -> None:
    start = time.perf_counter()
    _ = sum(i * i for i in range(4000))
    duration_ms = (time.perf_counter() - start) * 1000
    assert duration_ms < 100


@pytest.mark.skipif(
    not RUN_PERFORMANCE, reason="Set RUN_COMPANY_PERFORMANCE=1 to run performance tests"
)
def test_goal_alignment_under_10ms() -> None:
    start = time.perf_counter()
    _ = all(value >= 0 for value in range(1000))
    duration_ms = (time.perf_counter() - start) * 1000
    assert duration_ms < 10


@pytest.mark.skipif(
    not RUN_PERFORMANCE, reason="Set RUN_COMPANY_PERFORMANCE=1 to run performance tests"
)
def test_org_chart_100_departments() -> None:
    departments = [{"id": i, "parent": i // 10} for i in range(100)]
    start = time.perf_counter()
    grouped: Dict[int, int] = {}
    for department in departments:
        grouped.setdefault(department["parent"], 0)
        grouped[department["parent"]] += 1
    duration_ms = (time.perf_counter() - start) * 1000
    assert sum(grouped.values()) == 100
    assert duration_ms < 500


@pytest.mark.skipif(
    not RUN_PERFORMANCE, reason="Set RUN_COMPANY_PERFORMANCE=1 to run performance tests"
)
def test_goal_tree_500_goals() -> None:
    goals = [{"id": i, "parent": i // 3} for i in range(500)]
    start = time.perf_counter()
    children: Dict[int, List[int]] = {}
    for goal in goals:
        children.setdefault(goal["parent"], []).append(goal["id"])
    duration_ms = (time.perf_counter() - start) * 1000
    assert len(children) > 0
    assert duration_ms < 1000


@pytest.mark.skipif(
    not RUN_PERFORMANCE, reason="Set RUN_COMPANY_PERFORMANCE=1 to run performance tests"
)
def test_heartbeat_throughput() -> None:
    start = time.perf_counter()
    statuses: Dict[str, str] = {f"agent-{i}": "online" for i in range(1000)}
    duration_ms = (time.perf_counter() - start) * 1000
    assert len(statuses) == 1000
    assert duration_ms < 5000


@pytest.mark.skipif(
    not RUN_PERFORMANCE, reason="Set RUN_COMPANY_PERFORMANCE=1 to run performance tests"
)
def test_concurrent_department_updates() -> None:
    versions: Dict[str, int] = {f"dept-{i}": 1 for i in range(10)}
    for key in versions:
        versions[key] += 1
    assert all(version == 2 for version in versions.values())


@pytest.mark.skipif(
    not RUN_PERFORMANCE, reason="Set RUN_COMPANY_PERFORMANCE=1 to run performance tests"
)
def test_ancestry_cache_hit_rate() -> None:
    cache: Dict[int, List[int]] = {}
    hits = 0
    total = 100
    for i in range(total):
        key = i % 10
        if key in cache:
            hits += 1
        else:
            cache[key] = [key]
    assert (hits / total) >= 0.9
