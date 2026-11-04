"""
Autonomous Workflow Models Package

Re-exports models from the parent models.py for backwards compatibility.
"""

# Import from the actual models.py file (sibling file, not this directory)
import importlib.util
import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Any, Optional

# Get the path to models.py (sibling file)
_models_file = Path(__file__).parent.parent / "models.py"

WorkflowExperience: Any = None
__all__ = ["WorkflowExperience"]

if _models_file.exists():
    spec: ModuleSpec | None = importlib.util.spec_from_file_location(
        "autonomous_workflow_models_file", str(_models_file)
    )
    if spec is not None:
        _module = importlib.util.module_from_spec(spec)
        if spec.loader is not None:
            spec.loader.exec_module(_module)

            # Re-export WorkflowExperience
            if hasattr(_module, "WorkflowExperience"):
                WorkflowExperience = _module.WorkflowExperience
