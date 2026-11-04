"""
Audit script for agent YAML configuration files.

Validates all YAML files in a given directory against the
EnterpriseCatalogLoader validation logic and reports:
  - YAML parse errors
  - Missing required fields (agent name/class_name)
  - Duplicate normalized keys (silent overwrites)

Usage:
    python -m scripts.audit_agent_yaml [agent_dir]
    python -m scripts.audit_agent_yaml config/agents

Exit codes:
    0  All files valid, no duplicates
    1  Errors or duplicates found
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass
class AuditResult:
    """Result for a single YAML file audit."""

    filename: str
    normalized_key: Optional[str]
    status: str  # 'ok' | 'error' | 'duplicate'
    error: Optional[str] = None


@dataclass
class AuditReport:
    """Aggregated audit report for an agent directory."""

    results: List[AuditResult]
    agent_dir: str

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.status == "ok")

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.status == "error")

    @property
    def duplicate_count(self) -> int:
        return sum(1 for r in self.results if r.status == "duplicate")

    @property
    def errors(self) -> List[AuditResult]:
        return [r for r in self.results if r.status == "error"]

    @property
    def duplicates(self) -> List[AuditResult]:
        return [r for r in self.results if r.status == "duplicate"]


def _normalize_key(raw_config: Dict) -> Optional[str]:
    """
    Extract and normalize the agent key from a raw YAML config dict.

    Mirrors the logic in EnterpriseCatalogLoader._normalize_agent_config
    and _normalize_agent_key, but without importing from src/ so this
    script can run outside the full application context.

    Returns the normalized key string, or None if derivation fails.
    """
    if "agent_id" in raw_config:
        class_name = str(raw_config.get("class_name") or raw_config.get("name") or "")
    else:
        agent = raw_config.get("agent") or {}
        technical = raw_config.get("technical") or {}
        class_name = str(agent.get("name") or technical.get("class_name") or "").strip()

    if not class_name:
        return None

    # Bewuste KOPIE van EnterpriseCatalogLoader._normalize_agent_key (zie de docstring
    # hierboven). Dat de twee gelijk blijven wordt afgedwongen door
    # tests/architecture/test_de_twee_sleutelafleidingen_zijn_het_eens.py -- zonder die
    # toets loopt deze kopie stil uiteen zodra iemand de loader repareert.
    romp = class_name[: -len("Agent")] if class_name.endswith("Agent") else class_name
    return romp.lower() or class_name.lower()


def audit_agent_yaml(agent_dir: Path) -> AuditReport:
    """
    Audit all YAML files in agent_dir.

    Processes files in sorted order so results are deterministic.
    The first file to claim a normalized key wins (status='ok').
    Subsequent files with the same key are marked 'duplicate'.

    Args:
        agent_dir: Directory containing .yaml / .yml agent configs.

    Returns:
        AuditReport with per-file results.
    """
    results: List[AuditResult] = []
    seen_keys: Dict[str, str] = {}  # key -> first filename that claimed it

    yaml_files = sorted(p for p in Path(agent_dir).iterdir() if p.suffix in (".yaml", ".yml"))

    for yaml_file in yaml_files:
        filename = yaml_file.name

        # 1. Parse YAML
        try:
            with open(yaml_file, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            results.append(
                AuditResult(
                    filename=filename,
                    normalized_key=None,
                    status="error",
                    error=f"YAML parse error: {exc}",
                )
            )
            continue

        # 2. Derive normalized key
        key = _normalize_key(raw)
        if key is None:
            results.append(
                AuditResult(
                    filename=filename,
                    normalized_key=None,
                    status="error",
                    error="Missing agent.name / class_name",
                )
            )
            continue

        # 3. Check for duplicate key
        if key in seen_keys:
            results.append(
                AuditResult(
                    filename=filename,
                    normalized_key=key,
                    status="duplicate",
                    error=f"Key '{key}' already claimed by '{seen_keys[key]}'",
                )
            )
        else:
            seen_keys[key] = filename
            results.append(
                AuditResult(
                    filename=filename,
                    normalized_key=key,
                    status="ok",
                )
            )

    return AuditReport(results=results, agent_dir=str(agent_dir))


def _print_report(report: AuditReport) -> None:
    """Print a human-readable summary of the audit report."""
    print(f"Audit: {report.agent_dir}")
    print(f"  Total files : {report.total}")
    print(f"  OK          : {report.ok_count}")
    print(f"  Errors      : {report.error_count}")
    print(f"  Duplicates  : {report.duplicate_count}")

    if report.errors:
        print("\nErrors:")
        for r in report.errors:
            print(f"  [ERROR] {r.filename}: {r.error}")

    if report.duplicates:
        print("\nDuplicates (files that will be silently overwritten by the loader):")
        for r in report.duplicates:
            print(f"  [DUPE]  {r.filename}  (key={r.normalized_key!r}) -- {r.error}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit agent YAML config files for errors and duplicate keys."
    )
    parser.add_argument(
        "agent_dir",
        nargs="?",
        default=os.path.join("config", "agents"),
        help="Directory containing agent YAML files (default: config/agents)",
    )
    args = parser.parse_args(argv)

    agent_dir = Path(args.agent_dir)
    if not agent_dir.exists():
        print(f"ERROR: Directory not found: {agent_dir}", file=sys.stderr)
        return 1

    report = audit_agent_yaml(agent_dir)
    _print_report(report)

    if report.error_count > 0 or report.duplicate_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
