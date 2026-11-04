"""Architecture test: generated agents that call execute_tool() must have a profile.

Background (RV-002, 2026-06-27):
- 78 generated agents inherit execute_tool() via EnhancedBaseAgent.
- Currently 0 of them call it directly -- so default-deny is not hit in production.
- This test enforces that the moment a generated agent starts calling execute_tool(),
  its default agent_id must be registered in config/tool_permissions.yml.
  Without this guard the agent would silently fail at runtime with ToolExecutionException.
"""

import ast
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_AGENTS_DIR = REPO_ROOT / "src" / "core" / "agents" / "generated"
TOOL_PERMISSIONS_YML = REPO_ROOT / "config" / "tool_permissions.yml"

#: Zoveel .py-bestanden (excl. __init__.py e.d.) stonden er op 2026-09-08 in
#: GENERATED_AGENTS_DIR. Vloer met ruimte: een verplaatste/hernoemde map mag de scan
#: niet stil laten leeglopen -- dan zou geen enkel bestand meer op execute_tool()
#: gecontroleerd worden.
_MINIMUM_GENERATED_AGENT_FILES = 5


def _default_agent_id(source: str, pad: Path, fouten: list[str]) -> str | None:
    """Extract the default value of the agent_id parameter from __init__."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        fouten.append(f"{pad}: {exc}")
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            for arg, default in zip(reversed(node.args.args), reversed(node.args.defaults)):
                if arg.arg == "agent_id" and isinstance(default, ast.Constant):
                    return str(default.value)
    return None


def _calls_execute_tool(source: str, pad: Path, fouten: list[str]) -> bool:
    """Return True if the source contains a direct call to execute_tool(...)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        fouten.append(f"{pad}: {exc}")
        return False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute_tool"
            # Exclude calls on `self` only -- those would be base-class delegation,
            # not a direct generated-agent call. A direct call has the receiver as
            # something other than a simple `self` Name node, OR uses `await` on it.
        ):
            return True
    return False


def _registered_agent_ids() -> set[str]:
    """Return the set of agent_ids defined in tool_permissions.yml."""
    if not TOOL_PERMISSIONS_YML.exists():
        return set()
    with TOOL_PERMISSIONS_YML.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    profiles = (data or {}).get("agent_profiles", []) or []
    return {p["agent_id"] for p in profiles if isinstance(p, dict) and "agent_id" in p}


def _generated_agent_files() -> list[Path]:
    return [f for f in sorted(GENERATED_AGENTS_DIR.glob("*.py")) if not f.name.startswith("__")]


def _scan_generated_agents() -> tuple[list[str], list[str]]:
    """(violations, fouten) over alle generated agent-bestanden.

    Een bestand dat niet leest/parseert werd voorheen stil overgeslagen (except
    SyntaxError: return None/False, geen telling, geen vloer) -- precies het bestand
    met een echte niet-geregistreerde execute_tool()-aanroep kon zo ongezien buiten de
    scan vallen.
    """
    registered = _registered_agent_ids()
    violations: list[str] = []
    fouten: list[str] = []

    for agent_file in _generated_agent_files():
        try:
            source = agent_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            fouten.append(f"{agent_file}: {exc}")
            continue

        if not _calls_execute_tool(source, agent_file, fouten):
            continue  # agent does not use execute_tool -- no profile needed

        agent_id = _default_agent_id(source, agent_file, fouten)
        if agent_id is None:
            violations.append(
                f"{agent_file.name}: calls execute_tool() but default agent_id not found"
            )
        elif agent_id not in registered:
            violations.append(
                f"{agent_file.name}: calls execute_tool() with agent_id='{agent_id}'"
                f" but '{agent_id}' has no profile in {TOOL_PERMISSIONS_YML}"
            )

    return violations, fouten


def test_no_generated_agent_file_is_silently_unreadable_or_unparseable() -> None:
    """Vangnet: een overgeslagen bestand mag hier niet stil verdwijnen."""
    _, fouten = _scan_generated_agents()
    assert not fouten, (
        "Deze generated-agent-bestanden konden niet gelezen/geparsed worden en zijn NIET "
        "gecontroleerd op een ongeregistreerde execute_tool()-aanroep:\n"
        + "\n".join(f"  - {f}" for f in fouten)
    )


def test_the_scan_actually_finds_generated_agent_files() -> None:
    """Vangnet: een verplaatste/hernoemde map zou de scan stil laten leeglopen."""
    aantal = len(_generated_agent_files())
    assert aantal >= _MINIMUM_GENERATED_AGENT_FILES, (
        f"Slechts {aantal} .py-bestanden gevonden in {GENERATED_AGENTS_DIR} (verwacht "
        f">= {_MINIMUM_GENERATED_AGENT_FILES}). Is de map verplaatst of hernoemd? Dan "
        "controleert deze guard niets meer."
    )


def test_generated_agents_with_execute_tool_have_permission_profile() -> None:
    """Any generated agent that calls execute_tool() must have a profile in yml.

    If this test fails: add an entry to config/tool_permissions.yml for the
    agent_id listed in the failure message, with the tools that agent needs.
    """
    assert GENERATED_AGENTS_DIR.is_dir(), (
        f"Generated agents directory not found: {GENERATED_AGENTS_DIR}"
    )

    violations, _ = _scan_generated_agents()

    assert not violations, (
        "Generated agents call execute_tool() without a tool_permissions.yml profile.\n"
        "Add entries to config/tool_permissions.yml for each agent listed below:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
