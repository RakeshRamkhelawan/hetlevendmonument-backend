"""
Generate Agent YAML configurations from Markdown definitions.

Parses .md files with YAML frontmatter and generates structured YAML configs.
"""

import argparse
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class ParsedAgent:
    """Parsed agent definition from markdown."""

    name: str
    description: str
    model: str
    capabilities: List[str] = field(default_factory=list)
    ollama_model: Optional[str] = None
    role: str = "specialist"
    task_scope: str = "general"
    stack_layer: Optional[str] = None
    trigger_conditions: Dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    tools: List[str] = field(default_factory=list)
    collaborates_with: Dict[str, List[str]] = field(default_factory=dict)
    escalation_path: Dict[str, str] = field(default_factory=dict)
    output_format: str = "text"
    constraints: List[str] = field(default_factory=list)
    memory_type: str = "conversation"
    confidence_threshold: float = 0.7
    version: str = "1.0"
    tags: List[str] = field(default_factory=list)


@dataclass
class GenerationResult:
    """Result of YAML generation."""

    name: str
    output_path: Optional[Path]
    skipped: bool = False
    error: Optional[str] = None


def parse_agent_md(md_path: Path) -> Optional[ParsedAgent]:
    """Parse agent markdown file with YAML frontmatter.

    Args:
        md_path: Path to markdown file.

    Returns:
        ParsedAgent if valid, None otherwise.
    """
    content = md_path.read_text(encoding="utf-8")

    # Extract YAML frontmatter
    frontmatter_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not frontmatter_match:
        return None

    try:
        frontmatter = yaml.safe_load(frontmatter_match.group(1))
    except yaml.YAMLError:
        return None

    if not frontmatter or "name" not in frontmatter:
        return None

    # Extract capabilities from ## Capabilities section
    capabilities = []
    capabilities_match = re.search(
        r"##\s*Capabilities\s*\n(.*?)(?:\n##|\Z)", content, re.DOTALL | re.IGNORECASE
    )
    if capabilities_match:
        cap_section = capabilities_match.group(1)
        for line in cap_section.split("\n"):
            line = line.strip()
            if line.startswith("-"):
                capabilities.append(line[1:].strip())

    return ParsedAgent(
        name=frontmatter.get("name", ""),
        description=frontmatter.get("description", ""),
        model=frontmatter.get("model", "sonnet"),
        capabilities=capabilities if capabilities else ["General assistance"],
        ollama_model=frontmatter.get("ollama_model"),
        role=frontmatter.get("role", "specialist"),
        task_scope=frontmatter.get("task_scope", "general"),
        stack_layer=frontmatter.get("stack_layer"),
        trigger_conditions=frontmatter.get("trigger_conditions", {}),
        tools=frontmatter.get("tools", []),
        collaborates_with=frontmatter.get("collaborates_with", {}),
        escalation_path=frontmatter.get("escalation_path", {}),
        output_format=frontmatter.get("output_format", "text"),
        constraints=frontmatter.get("constraints", []),
        memory_type=frontmatter.get("memory_type", "conversation"),
        confidence_threshold=frontmatter.get("confidence_threshold", 0.7),
        version=frontmatter.get("version", "1.0"),
        tags=frontmatter.get("tags", []),
    )


def _to_pascal_case(name: str) -> str:
    """Convert snake-case or kebab-case to PascalCase."""
    return "".join(word.capitalize() for word in re.split(r"[-_]", name))


def _infer_department(agent: ParsedAgent) -> str:
    """Infer department from agent name/tags/stack_layer."""
    name_lower = agent.name.lower()
    tags_lower = [t.lower() for t in agent.tags]

    # Check tags first
    if "security" in tags_lower:
        return "it_security"
    if "hr" in tags_lower or "human_resources" in tags_lower:
        return "hr"
    if "finance" in tags_lower or "accounting" in tags_lower:
        return "finance"
    if "marketing" in tags_lower:
        return "marketing"
    if "legal" in tags_lower or "compliance" in tags_lower:
        return "legal"
    if "operations" in tags_lower:
        return "operations"

    # Check stack_layer
    if agent.stack_layer:
        layer_lower = agent.stack_layer.lower()
        if layer_lower in ("data", "analytics"):
            return "data_engineering"
        if layer_lower == "infrastructure":
            return "infrastructure"
        if layer_lower == "security":
            return "it_security"

    # Check name patterns
    if "security" in name_lower:
        return "it_security"
    if "hr" in name_lower:
        return "hr"
    if "finance" in name_lower or "accounting" in name_lower:
        return "finance"

    # Default
    return "software_engineering"


def generate_agent_yaml(agent: ParsedAgent) -> str:
    """Generate YAML configuration from parsed agent.

    Args:
        agent: Parsed agent definition.

    Returns:
        YAML string.
    """
    class_name = _to_pascal_case(agent.name) + "Agent"
    department = _infer_department(agent)

    # Map model to priority
    priority_map = {
        "gpt-4": "HIGH",
        "gpt-4o": "HIGH",
        "sonnet": "MEDIUM",
        "haiku": "MEDIUM",
        "gpt-3.5": "MEDIUM",
        "ollama": "LOW",
    }
    priority = "MEDIUM"
    for key, val in priority_map.items():
        if key in agent.model.lower():
            priority = val
            break

    config = {
        "agent": {
            "name": class_name,
            "description": agent.description,
            "version": agent.version,
        },
        "classification": {
            "department": department,
            "role": agent.role.upper(),
            "task_scope": agent.task_scope,
        },
        "technical": {
            "technology": "LLM",
            "class_name": class_name,
            "ollama_model": agent.ollama_model,
        },
        "behaviour": {
            "priority": priority,
            "tools": agent.tools if agent.tools else ["general_assistance"],
        },
        "metadata": {
            "description": agent.description,
            "tags": agent.tags,
        },
        "capabilities": agent.capabilities,
        "ooda_profile": {
            "observe": {
                "input_format": agent.output_format,
            },
            "orient": {
                "memory_type": agent.memory_type,
            },
            "decide": {
                "confidence_threshold": agent.confidence_threshold,
            },
            "act": {
                "tools": agent.tools if agent.tools else ["general_assistance"],
            },
        },
    }

    # Remove None values
    def remove_none(d: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
        if isinstance(d, dict):
            return {k: remove_none(v) for k, v in d.items() if v is not None}
        return d

    config = remove_none(config)

    return yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)


def generate_all_agent_yaml(
    agents_dir: Path, output_dir: Path, force: bool = False, verbose: bool = False
) -> List[GenerationResult]:
    """Generate YAML for all agents in directory.

    Args:
        agents_dir: Directory containing .md agent definitions.
        output_dir: Directory to write YAML files.
        force: Overwrite existing files.
        verbose: Print progress.

    Returns:
        List of GenerationResult.
    """
    results = []

    if not agents_dir.exists():
        raise FileNotFoundError(f"Agents directory does not exist: {agents_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    for md_file in agents_dir.glob("*.md"):
        agent = parse_agent_md(md_file)
        if not agent:
            continue

        output_path = output_dir / f"{agent.name}.yaml"

        if output_path.exists() and not force:
            results.append(GenerationResult(name=agent.name, output_path=output_path, skipped=True))
            if verbose:
                print(f"Skipped {agent.name} (already exists)")
            continue

        yaml_content = generate_agent_yaml(agent)
        output_path.write_text(yaml_content, encoding="utf-8")

        results.append(GenerationResult(name=agent.name, output_path=output_path))
        if verbose:
            print(f"Generated {agent.name} -> {output_path}")

    return results


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate agent YAML from markdown definitions")
    parser.add_argument(
        "--agents-dir", type=Path, required=True, help="Directory containing .md agent files"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./output"),
        help="Directory to write YAML files (default: ./output)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing YAML files")
    parser.add_argument("--dry-run", action="store_true", help="Don't write any files")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print progress")

    args = parser.parse_args()

    if not args.agents_dir.exists():
        print(
            f"Error: Agents directory does not exist: {args.agents_dir}",
            file=__import__("sys").stderr,
        )
        return 1

    if args.dry_run:
        print("dry-run mode - no files will be written")
        return 0

    try:
        results = generate_all_agent_yaml(
            args.agents_dir, args.output_dir, force=args.force, verbose=args.verbose
        )
        if args.verbose:
            print(f"\nGenerated {len([r for r in results if not r.skipped])} files")
            print(f"Skipped {len([r for r in results if r.skipped])} files")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    exit(main())
