"""Architecture-test specific setup.

DSM architecture tests import local utility scripts (``scripts.dsm_full_analysis``).
Some CI environments have a top-level ``scripts`` namespace package in site-packages
that shadows the repository's ``scripts`` directory. This conftest forces the local
package to be loaded before any architecture test module is imported.
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_SCRIPTS_INIT = _PROJECT_ROOT / "scripts" / "__init__.py"

# Ensure repo root is on the path first.
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# If a non-local `scripts` package was already loaded (e.g. from site-packages),
# evict it and its submodules so the local scripts package is discovered.
if "scripts" in sys.modules:
    existing = sys.modules["scripts"]
    if getattr(existing, "__file__", None) != str(_LOCAL_SCRIPTS_INIT):
        del sys.modules["scripts"]
        for name in list(sys.modules):
            if name.startswith("scripts."):
                del sys.modules[name]

# Prime the local scripts package.
import scripts  # noqa: E402
