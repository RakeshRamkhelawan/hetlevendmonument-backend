"""Architecture tests tracking TC-001/TC-008 test reactivation backlog.

These tests stay RED until the quarantined tests are properly reactivated.
Per quality-gates.md: every FA-bevinding naar backlog vereist een falende architecture test.

TC-001: Mission endpoint tests (temp_disabled/test_mission_endpoints.py)
TC-008: Users endpoint tests (temp_disabled/api/v1/test_users.py)
"""

from pathlib import Path

QUARANTINE_DIR = Path("tests/unit/temp_disabled")


def test_tc_001_mission_tests_not_in_quarantine() -> None:
    """TC-001: Mission endpoint tests must be reactivated out of temp_disabled.

    TODO(SP-AUDIT-FIX-001): Rewrite test_mission_endpoints.py against MissionORM
    (removed helpers: _create_sample_mission / _missions_store / _save_mission).
    """
    mission_test = QUARANTINE_DIR / "test_mission_endpoints.py"
    assert not mission_test.exists(), (
        "tests/unit/temp_disabled/test_mission_endpoints.py still quarantined -- "
        "TC-001: rewrite against MissionORM and move to tests/unit/api/ to resolve"
    )


def test_tc_001_sp_a01_missions_behavioral_not_in_quarantine() -> None:
    """TC-001: SP-A01 missions behavioral tests must be reactivated.

    TODO(SP-AUDIT-FIX-001): Rewrite test_sp_a01_missions_behavioral.py.
    """
    mission_behavioral = QUARANTINE_DIR / "test_sp_a01_missions_behavioral.py"
    assert not mission_behavioral.exists(), (
        "tests/unit/temp_disabled/test_sp_a01_missions_behavioral.py still quarantined -- "
        "TC-001: rewrite against current mission API and move to tests/unit/api/"
    )


def test_tc_008_users_tests_not_in_quarantine() -> None:
    """TC-008: Users endpoint tests must be reactivated out of temp_disabled.

    TODO(SP-AUDIT-FIX-001): Rewrite test_users.py with proper unit-test fixtures
    (current version requires integration-test async_client + admin_token).
    """
    users_test = QUARANTINE_DIR / "api" / "v1" / "test_users.py"
    assert not users_test.exists(), (
        "tests/unit/temp_disabled/api/v1/test_users.py still quarantined -- "
        "TC-008: rewrite as unit test with mocked DB and move to tests/unit/api/v1/"
    )
