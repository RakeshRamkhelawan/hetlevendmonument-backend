"""
migrate_agent_definitions.py
Adds new schema-field skeleton to .md frontmatter without overwriting existing values.
Usage: python scripts/migrate_agent_definitions.py [--dry-run] [--layer specialist]
"""

from __future__ import annotations

import argparse
from pathlib import Path

NEW_FIELDS_SKELETON = """
role: ""
task_scope: ""
stack_layer: ""
trigger_conditions:
  type: ""
  description: ""
tools: []
collaborates_with:
  calls: []
  called_by: []
escalation_path:
  on_failure: ""
  on_low_confidence: ""
  on_out_of_scope: ""
output_format: ""
constraints: []
memory_type: ""
confidence_threshold: 0.7
version: "1.0.0"
tags: []
"""


def migrate_md_file(path: Path, dry_run: bool = False) -> str:
    content = path.read_text(encoding="utf-8")

    if not content.startswith("---"):
        return f"SKIP (no frontmatter): {path.name}"

    if "stack_layer" in content:
        return f"SKIP (already migrated): {path.name}"

    parts = content.split("---", 2)
    if len(parts) < 3:
        return f"SKIP (invalid frontmatter): {path.name}"

    parts[1] = parts[1].rstrip() + "\n" + NEW_FIELDS_SKELETON
    new_content = "---".join(parts)

    if not dry_run:
        path.write_text(new_content, encoding="utf-8")

    return f"MIGRATED: {path.name}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate .md agent definitions to Standard v1.0")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files",
    )
    parser.add_argument(
        "--dir",
        default="src/core/agents",
        help="Directory containing .md agent files",
    )
    args = parser.parse_args()

    agents_dir = Path(args.dir)
    if not agents_dir.exists():
        print(f"ERROR: directory not found: {agents_dir}")
        raise SystemExit(1)

    md_files = sorted(agents_dir.glob("*.md"))
    results = [migrate_md_file(f, dry_run=args.dry_run) for f in md_files]

    for r in results:
        print(r)

    migrated = sum(1 for r in results if r.startswith("MIGRATED"))
    skipped = len(results) - migrated
    print(f"\nDone: {migrated} migrated, {skipped} skipped")
    if args.dry_run:
        print("(dry-run - no files modified)")


if __name__ == "__main__":
    main()
