"""SP-AUDIT-004: log_action() moet altijd session=db meekrijgen.

Patroon conform test_profile_router_audit.py (file-read + paren-tracking).
Rode tests -- ROOD voor fix, GROEN na session=db toegevoegd aan alle call-sites.
"""

from pathlib import Path

import pytest


def _calls_without_session(src: str) -> list[int]:
    """Return 1-based indices of log_action() calls missing session= in args."""
    missing = []
    parts = src.split("log_action(")
    for idx, part in enumerate(parts[1:], start=1):
        depth = 1
        for i, ch in enumerate(part):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    args = part[:i]
                    if "session=" not in args:
                        missing.append(idx)
                    break
    return missing


@pytest.mark.parametrize(
    "rel_path,label",
    [
        (
            "src/core/api/v1/user_management/crud_router.py",
            "user_management/crud_router",
        ),
        (
            "src/core/api/v1/user_management/profile_router.py",
            "user_management/profile_router",
        ),
        (
            "src/core/api/v1/documents/crud_router.py",
            "documents/crud_router",
        ),
        (
            "src/core/api/v1/documents/processing_router.py",
            "documents/processing_router",
        ),
        (
            "src/core/api/v1/documents/upload_router.py",
            "documents/upload_router",
        ),
        (
            "src/core/api/v1/notifications/router.py",
            "notifications/router",
        ),
        (
            "src/core/api/v1/tenant_management/crud_router.py",
            "tenant_management/crud_router",
        ),
    ],
)
def test_log_action_calls_have_session(rel_path: str, label: str) -> None:
    """ADR-019: elke log_action() aanroep moet session= meekrijgen.

    Zonder session= wordt de audit entry niet naar de DB geschreven --
    log_action() retourneert stil None (ADR-019 schending).
    SP-AUDIT-004 rode test -- ROOD voor fix-commit.
    """
    src = Path(rel_path).read_text(encoding="utf-8-sig")
    missing = _calls_without_session(src)
    assert not missing, (
        f"{label}: {len(missing)} log_action() aanroep(en) zonder session= "
        f"(call #{missing}) -- ADR-019 schending"
    )
