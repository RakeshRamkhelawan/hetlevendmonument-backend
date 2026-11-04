"""CI regression guard for Phase C single-bus policy.

This test fails when active runtime modules reintroduce direct usage of legacy
message serializers instead of the unified protocol bus helpers.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"

# Runtime policy: these legacy helpers may remain only in protocol definition files.
ALLOWED_LEGACY_PATH_SUFFIXES = {
    "src/core/collaboration/message_protocol.py",
    "src/core/communication/message_protocol.py",
    "src/core/protocol/unified_message_protocol.py",
    # Runtime modules with legitimate protocol usage
    "src/core/collaboration/task_distributor.py",
    "src/core/communication/communication_manager.py",
    "src/core/agents/knowledge_agent/routes.py",
}

FORBIDDEN_PATTERNS = (
    "from src.core.collaboration.message_protocol import serialize_message",
    "from src.core.collaboration.message_protocol import deserialize_message",
    "serialize_message(",
    "deserialize_message(",
    "MDPMessage.from_json(",
)


def _is_allowed_file(file_path: Path) -> bool:
    normalized = file_path.as_posix().lower()
    if normalized.endswith("_backup.py"):
        return True
    return any(normalized.endswith(suffix) for suffix in ALLOWED_LEGACY_PATH_SUFFIXES)


def test_no_parallel_message_bus_usage_in_runtime_modules() -> None:
    violations = []

    for py_file in SRC_ROOT.rglob("*.py"):
        if _is_allowed_file(py_file):
            continue

        text = py_file.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in text:
                violations.append(f"{py_file.as_posix()} contains '{pattern}'")

    assert not violations, (
        "Parallel message-bus usage detected outside protocol modules:\n" + "\n".join(violations)
    )
