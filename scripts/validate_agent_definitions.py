"""
validate_agent_definitions.py
Validates .md frontmatter against Agent Definition Standard v1.0.
Usage: python scripts/validate_agent_definitions.py [--report]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FIELDS = [
    "name",
    "role",
    "description",
    "task_scope",
    "stack_layer",
    "trigger_conditions",
    "tools",
    "collaborates_with",
    "escalation_path",
    "output_format",
    "constraints",
    "memory_type",
    "confidence_threshold",
    "version",
]

_PLACEHOLDER_VALUES = {
    "see capabilities section",
    "code-based agent implementation",
    "specialized task handling",
    "als agent:",
}


def _is_placeholder(val: object) -> bool:
    if not isinstance(val, str):
        return False
    if not val.strip():  # empty or whitespace-only string
        return True
    normalized = val.strip().lower().rstrip(".")
    return any(normalized.startswith(p) for p in _PLACEHOLDER_VALUES)


def _nested_empty_lists(val: object) -> list[str]:
    """Return keys of any empty lists nested inside a dict value."""
    if not isinstance(val, dict):
        return []
    return [k for k, v in val.items() if isinstance(v, list) and len(v) == 0]


@dataclass
class MDValidationResult:
    agent_name: str
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    completion_pct: float = 0.0


class MDFrontmatterValidator:
    """Validates .md frontmatter against Agent Definition Standard v1.0."""

    def validate_file(self, path: Path) -> MDValidationResult:
        content = path.read_text(encoding="utf-8")
        agent_name = path.stem
        errors: list[str] = []
        warnings: list[str] = []

        if not content.startswith("---"):
            return MDValidationResult(agent_name, False, errors=["No YAML frontmatter found"])

        try:
            fm_text = content.split("---", 2)[1]
            fm: dict[str, Any] = yaml.safe_load(fm_text) or {}  # TODO(TYPE): replace Any with concrete type
        except yaml.YAMLError as exc:
            return MDValidationResult(agent_name, False, errors=[f"YAML parse error: {exc}"])

        filled = 0.0
        for f in REQUIRED_FIELDS:
            val = fm.get(f)
            if val is None:
                errors.append(f"Missing: '{f}'")
            elif _is_placeholder(val):
                warnings.append(f"Placeholder value: '{f}' = {str(val)[:60]!r}")
                filled += 0.5
            elif isinstance(val, list) and len(val) == 0:
                warnings.append(f"Empty list: '{f}'")
                filled += 0.5
            elif isinstance(val, dict):
                empty_sub = _nested_empty_lists(val)
                if empty_sub:
                    warnings.append(f"Empty nested lists in '{f}': {empty_sub}")
                    filled += 0.7
                else:
                    filled += 1
            else:
                filled += 1

        # Quality checks
        role = str(fm.get("role", ""))
        if role and len(role) > 120:
            warnings.append(f"'role' too lang ({len(role)} chars, max 120)")

        constraints = fm.get("constraints", [])
        if isinstance(constraints, list) and 0 < len(constraints) < 3:
            warnings.append(f"'constraints' has {len(constraints)} item(s), minimum 3 recommended")

        completion_pct = round((filled / len(REQUIRED_FIELDS)) * 100, 1)
        return MDValidationResult(agent_name, len(errors) == 0, errors, warnings, completion_pct)

    def validate_directory(self, directory: Path) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        md_files = sorted(f for f in directory.glob("*.md") if "kopie" not in f.name)
        results = [self.validate_file(f) for f in md_files]
        valid = [r for r in results if r.is_valid]
        avg = sum(r.completion_pct for r in results) / len(results) if results else 0.0
        return {
            "total": len(results),
            "valid": len(valid),
            "invalid": len(results) - len(valid),
            "avg_completion_pct": round(avg, 1),
            "details": [vars(r) for r in results],
        }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate .md agent definitions")
    parser.add_argument("--report", action="store_true", help="Write JSON report")
    parser.add_argument("--dir", default="src/core/agents", help="Directory with .md files")
    args = parser.parse_args()

    validator = MDFrontmatterValidator()
    summary = validator.validate_directory(Path(args.dir))

    print("\n=== Agent Definition Validation Report ===")
    print(
        f"Total: {summary['total']} | Valid: {summary['valid']} | "
        f"Invalid: {summary['invalid']} | Avg completion: {summary['avg_completion_pct']}%\n"
    )

    for agent in summary["details"]:
        icon = "+" if agent["is_valid"] else "x"
        print(f"{icon} {agent['agent_name']:45} {agent['completion_pct']}%")
        for err in agent["errors"]:
            print(f"     ERROR: {err}")
        for warn in agent["warnings"]:
            print(f"     WARN:  {warn}")

    if args.report:
        report_path = Path("agent_validation_report.json")
        report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
