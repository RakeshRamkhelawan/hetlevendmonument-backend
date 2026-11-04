"""TDD test for CI workflow type check step (B3.1)."""

import yaml
from pathlib import Path


def test_ci_has_type_check_step():
    """RED: CI workflow must have a type check or pyright step."""
    workflow_path = Path(".github/workflows/ci-feature.yml")
    assert workflow_path.exists(), "ci-feature.yml must exist"
    with open(workflow_path, encoding="utf-8") as f:
        workflow = yaml.safe_load(f)
    jobs = workflow.get("jobs", {})
    found = False
    for job_name, job in jobs.items():
        for step in job.get("steps", []):
            name = step.get("name", "").lower()
            if "type check" in name or "pyright" in name:
                found = True
    assert found, "CI workflow must have a type check step"
