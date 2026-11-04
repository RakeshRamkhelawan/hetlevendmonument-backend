"""SP-S01: Tests for chain_verifier timestamp-sort fix + DSAR/PolicyChange tenant payload fix.

B-004: chain_verifier sorted by timestamp (non-deterministic at concurrency) -> hash-link traversal
B-005: DSARExport + PolicyChange read tenant_id from user-controlled payload -> server-side lookup
"""

import pathlib
import pytest

_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.mark.unit
class TestChainVerifierB004:
    def test_chain_verifier_does_not_sort_by_timestamp(self) -> None:
        """chain_verifier must NOT sort by timestamp -- timestamps collide under concurrent writes."""
        source = (_ROOT / "src/core/copilot/audit/chain_verifier.py").read_text()
        # Detect the bad pattern: order_by(...timestamp...)
        has_timestamp_sort = (
            "order_by" in source.lower() and "timestamp" in source.lower() and ".asc()" in source
        )
        assert not has_timestamp_sort, (
            "chain_verifier still sorts by timestamp -- B-004 not fixed. "
            "Use hash-link traversal (previous_hash) instead of ORDER BY timestamp."
        )

    def test_chain_verifier_uses_hash_link_traversal(self) -> None:
        """chain_verifier must traverse the chain via previous_hash (linked-list)."""
        source = (_ROOT / "src/core/copilot/audit/chain_verifier.py").read_text()
        assert "previous_hash" in source, (
            "chain_verifier has no previous_hash traversal -- linked-list missing (B-004)"
        )

    def test_chain_verifier_handles_genesis_record(self) -> None:
        """chain_verifier must explicitly handle the genesis record (previous_hash is None)."""
        source = (_ROOT / "src/core/copilot/audit/chain_verifier.py").read_text()
        assert "previous_hash is None" in source or "previous_decision_hash is None" in source, (
            "chain_verifier does not identify genesis record via previous_hash=None (B-004)"
        )

    def test_chain_verifier_detects_circular_chain(self) -> None:
        """chain_verifier must protect against circular chains (seen-set guard)."""
        source = (_ROOT / "src/core/copilot/audit/chain_verifier.py").read_text()
        assert "seen" in source, (
            "chain_verifier has no cycle-detection (seen set) -- circular chain would hang (B-004)"
        )


@pytest.mark.unit
class TestDSARMonitorTenantSafetyB005:
    def test_dsar_export_does_not_read_tenant_from_payload(self) -> None:
        """DSARExport must NOT trust tenant_id from payload (CLAUDE.md sec 6.1)."""
        source = (_ROOT / "src/core/copilot/proactive/monitors/dsar_export.py").read_text()
        assert 'payload.get("tenant_id")' not in source, (
            "DSARExport reads tenant_id from payload -- CLAUDE.md sec 6.1 violation (B-005). "
            "Derive tenant_id from a server-side source (e.g. user lookup via TenantRepo)."
        )
        assert "payload['tenant_id']" not in source, (
            "DSARExport reads tenant_id from payload via dict access -- CLAUDE.md sec 6.1 (B-005)"
        )

    def test_dsar_export_derives_tenant_from_server_side_source(self) -> None:
        """DSARExport must derive tenant_id from a server-side source (TenantRepo)."""
        source = (_ROOT / "src/core/copilot/proactive/monitors/dsar_export.py").read_text()
        # After fix: must use a TenantRepo method to look up tenant
        assert "get_tenant_id_for_user" in source, (
            "DSARExport must call tenant_repo.get_tenant_id_for_user(user_id) "
            "to derive tenant_id from user_id (server-side) -- B-005"
        )

    def test_dsar_export_rejects_unknown_user(self) -> None:
        """DSARExport must reject events where user_id maps to no tenant (guard against spoofing)."""
        source = (_ROOT / "src/core/copilot/proactive/monitors/dsar_export.py").read_text()
        # Must have a None check after the lookup
        assert "tenant_id is None" in source or "if not tenant_id" in source, (
            "DSARExport does not reject None tenant (unknown user_id) -- B-005"
        )

    def test_policy_change_does_not_read_tenant_from_payload(self) -> None:
        """PolicyChange must NOT trust tenant_id from payload (CLAUDE.md sec 6.1)."""
        source = (_ROOT / "src/core/copilot/proactive/monitors/policy_change.py").read_text()
        assert 'payload.get("tenant_id")' not in source, (
            "PolicyChange reads tenant_id from payload -- CLAUDE.md sec 6.1 violation (B-005)"
        )
        assert "payload['tenant_id']" not in source, (
            "PolicyChange reads tenant_id from payload via dict access -- B-005"
        )

    def test_policy_change_derives_tenant_from_server_side_source(self) -> None:
        """PolicyChange must derive tenant_id from a server-side source (TenantRepo)."""
        source = (_ROOT / "src/core/copilot/proactive/monitors/policy_change.py").read_text()
        assert "get_tenant_id_for_workflow" in source, (
            "PolicyChange must call tenant_repo.get_tenant_id_for_workflow(workflow_id) "
            "to derive tenant_id server-side -- B-005"
        )

    def test_policy_change_rejects_unknown_workflow(self) -> None:
        """PolicyChange must reject events where workflow_id maps to no tenant."""
        source = (_ROOT / "src/core/copilot/proactive/monitors/policy_change.py").read_text()
        assert "tenant_id is None" in source or "if not tenant_id" in source, (
            "PolicyChange does not reject None tenant (unknown workflow_id) -- B-005"
        )
