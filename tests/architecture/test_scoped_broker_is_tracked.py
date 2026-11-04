"""Architecture guard: runtime-imported source under src/services/ MUST be git-tracked.

F1 (dag-9): src/services/tool_broker/scoped_broker.py was never committed (a local
.git/info/exclude rule hid src/services/), so it existed on developers' disks but was
absent from every fresh clone. The lazy import in _build_copilot_service
(src/core/copilot/dependencies.py) therefore made every POST /api/v1/copilot/turn raise
ModuleNotFoundError in CI/staging/production while passing locally. This test fails the
moment a runtime-imported module under src/services/ is not tracked, so the class of
regression cannot recur silently.
"""

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Modules under src/services/ that are imported by tracked runtime code and therefore
# MUST be present in a fresh clone. scoped_broker is imported by the copilot turn path.
_REQUIRED_TRACKED_FILES = [
    "src/services/tool_broker/scoped_broker.py",
]


def _git_tracked_files() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files", "src/services"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    # git ls-files always uses forward slashes.
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


def test_runtime_services_modules_are_git_tracked():
    """A runtime-imported module under src/services/ that is not git-tracked would
    500 on a fresh clone (F1). Every required file must appear in `git ls-files`."""
    tracked = _git_tracked_files()
    missing = [f for f in _REQUIRED_TRACKED_FILES if f not in tracked]
    assert not missing, (
        "These runtime-imported src/services modules are NOT git-tracked and would "
        "cause ModuleNotFoundError on a fresh clone (F1 class): " + ", ".join(missing)
    )
