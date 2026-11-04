"""SP-DSM-009: auth<->infra and agent_runtime<->infra circular pairs must be eliminated.

These tests verify that the two MEDIUM circular pairs identified after SP-DSM-008 are gone.
A circular pair disappears when either direction reaches 0 imports.
"""

from __future__ import annotations

from pathlib import Path

from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module

_REPO_ROOT = Path(__file__).parents[2]


def _compute_pair_counts(bucket_a: str, bucket_b: str) -> tuple[int, int]:
    """Return (a_to_b, b_to_a) import counts between two buckets."""
    dirs_a = SOURCE_DIRS.get(bucket_a, [])
    dirs_b = SOURCE_DIRS.get(bucket_b, [])
    counts_a, _, _ = scan_module(bucket_a, [str(_REPO_ROOT / d) for d in dirs_a])
    counts_b, _, _ = scan_module(bucket_b, [str(_REPO_ROOT / d) for d in dirs_b])
    return counts_a.get(bucket_b, 0), counts_b.get(bucket_a, 0)


def test_dsm_no_auth_infra_circular_pair():
    """auth <-> infra circular pair must be gone -- SP-DSM-009.

    The cycle is broken when infra->auth = 0 (scheduling/api routes moved to
    core_api, seed.py passlib-direct, vibe_monitoring.py moved to integrations).
    """
    _, infra_to_auth = _compute_pair_counts("auth", "infra")
    assert infra_to_auth == 0, (
        f"infra->auth backward still has {infra_to_auth} import(s). "
        "Fix: move remaining infra files that import auth to core_api/integrations."
    )


def test_dsm_no_agent_runtime_infra_circular_pair():
    """agent_runtime <-> infra circular pair must be gone -- SP-DSM-009.

    The cycle is broken when infra->agent_runtime = 0 (container.py moved to
    agent_runtime SOURCE_DIRS so its lazy agent_runtime imports are same-bucket).
    """
    _, infra_to_ar = _compute_pair_counts("agent_runtime", "infra")
    assert infra_to_ar == 0, (
        f"infra->agent_runtime backward still has {infra_to_ar} import(s). "
        "Fix: move container.py from infra to agent_runtime in SOURCE_DIRS."
    )
