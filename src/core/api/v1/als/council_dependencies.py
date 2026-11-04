# dsm:exempt reason: Laag 1 facade voor copilot.council -- apart van als/dependencies.py
# om circular import te vermijden (als/deps -> copilot.council.factory -> als.*)
"""ALS council FastAPI dependencies -- kept separate from als/dependencies.py.

Separation reason: als/dependencies.py -> copilot.council.factory -> als.* creates a
circular import chain at module scope. This file is NOT imported by any als.* submodule.
"""

from src.core.copilot.council.factory import build_council
from src.core.copilot.council.governance_gate import require_council_approval

__all__ = ["build_council", "require_council_approval"]
