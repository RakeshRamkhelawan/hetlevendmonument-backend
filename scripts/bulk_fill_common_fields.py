"""
bulk_fill_common_fields.py
Fills common (agent-type-invariant) fields for all .md specialist agents.
Only fills fields that are still empty/null - never overwrites filled values.
Usage: python scripts/bulk_fill_common_fields.py [--dry-run]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

# Fields identical for every .md specialist agent.
# collaborates_with.calls is intentionally empty - must be filled per-agent
# in Tasks 10-14 (some agents call critic_agent, some call peers, some call none).
COMMON_DEFAULTS: dict = {
    "stack_layer": "specialist",
    "memory_type": "none",
    "confidence_threshold": 0.7,
    "version": "1.0.0",
    "trigger_conditions": {
        "type": "intelligent",
        "description": "",  # must be filled per-agent
    },
    "collaborates_with": {
        "calls": [],  # filled per-agent in Tasks 10-14
        "called_by": ["MasterOrchestratorAgent", "AgentRouterAgent"],
    },
    "escalation_path": {
        "on_failure": "MasterOrchestratorAgent",
        "on_low_confidence": "MasterOrchestratorAgent",
        "on_out_of_scope": "AgentRouterAgent",
    },
    "tools": ["llm_client"],
}


def _is_empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def bulk_fill_md_file(path: Path, dry_run: bool = False) -> str:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return f"SKIP (geen frontmatter): {path.name}"

    parts = content.split("---", 2)
    if len(parts) < 3:
        return f"SKIP (invalid frontmatter): {path.name}"

    try:
        fm: dict = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        return f"SKIP (YAML fout): {path.name} - {exc}"

    changed = False
    for key, default in COMMON_DEFAULTS.items():
        current = fm.get(key)
        if isinstance(default, dict) and isinstance(current, dict):
            # Merge sub-keys without overwriting filled values
            for sub_key, sub_default in default.items():
                if _is_empty(current.get(sub_key)):
                    current[sub_key] = sub_default
                    changed = True
        elif _is_empty(current):
            fm[key] = default
            changed = True

    if not changed:
        return f"SKIP (no empty fields): {path.name}"

    if not dry_run:
        new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
        parts[1] = "\n" + new_fm
        path.write_text("---".join(parts), encoding="utf-8")

    return f"FILLED: {path.name}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dir", default="src/core/agents")
    args = parser.parse_args()

    agents_dir = Path(args.dir)
    md_files = sorted(agents_dir.glob("*.md"))
    results = [bulk_fill_md_file(f, dry_run=args.dry_run) for f in md_files]

    for r in results:
        print(r)

    filled = sum(1 for r in results if r.startswith("FILLED"))
    print(f"\nDone: {filled}/{len(results)} files updated")


if __name__ == "__main__":
    main()
