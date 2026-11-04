"""Tool Permission Manager - least-privilege enforcement for agents.

See: docs/adr/015-agent-tool-execution-safety-allowlist-and-audit.md
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from loguru import logger


@dataclass
class AgentToolProfile:
    """Tool permission profile for an agent."""

    agent_id: str
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    # ADR-036 D5 -- harde denylist ("nooit aanraken", AI Act art. 14). Wordt gecontroleerd
    # VOOR de Council/HITL-poort, zodat geen menselijke goedkeuring dit kan overrulen.
    #
    # Reconciliatie met denied_tools (D5, verplicht): `denied_tools` is de legacy-alias en
    # functioneel een deelverzameling; `denied_actions` is leidend voor nieuwe profielen.
    # Beide worden gehandhaafd -- de UNIE is verboden -- zodat een bestaand profiel niet
    # stilzwijgend losser wordt zodra iemand alleen het nieuwe veld invult.
    denied_actions: list[str] = field(default_factory=list)
    max_tools: int = 10  # Least-privilege guardrail per ADR-015


class ToolPermissionManager:
    """Manages tool permissions with least-privilege principle.

    Resolution order for is_tool_allowed():
    1. Harde denylist: denied_actions UNIE denied_tools (expliciete deny wint altijd)
    2. Allowed list check
    3. No profile -> False (ADR-015 default-deny, RC-007 fix)

    ADR-036 D5: `denied_actions` is de "nooit aanraken"-laag (AI Act art. 14). Deze check
    draait op stap 0 van ToolBrokerService.execute_tool -- dus VOOR de risk-classificatie
    en de HITL/Council-poort. Die volgorde hoort bij het contract: zou de Council er eerst
    iets van mogen vinden, dan is de denylist per definitie overrulebaar en dus geen harde
    laag. Bewaakt door tests/unit/tool_broker/test_denied_actions_hard_denylist.py.
    """

    def __init__(self, config_path: str | None = None) -> None:
        self._agent_profiles: dict[str, AgentToolProfile] = {}
        self._load_config(config_path)

    def _load_config(self, config_path: str | None) -> None:
        """Load tool permission profiles from YAML config."""
        if config_path is None:
            config_path = str(
                Path(__file__).parent.parent.parent.parent / "config" / "tool_permissions.yml"
            )

        path = Path(config_path)
        if not path.exists():
            logger.warning("Tool permission config not found at {}, using defaults", path)
            return

        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                return

            for profile_data in data.get("agent_profiles", []):
                profile = AgentToolProfile(
                    agent_id=profile_data["agent_id"],
                    allowed_tools=list(profile_data.get("allowed_tools", []) or []),
                    denied_tools=list(profile_data.get("denied_tools", []) or []),
                    denied_actions=list(profile_data.get("denied_actions", []) or []),
                    max_tools=profile_data.get("max_tools", 10),
                )
                self._agent_profiles[profile.agent_id] = profile

            logger.debug(
                "Loaded tool permission profiles for {} agents",
                len(self._agent_profiles),
            )

        except (yaml.YAMLError, KeyError, TypeError, ValueError) as e:
            logger.error("Failed to load tool permissions: {}", e)

    def validate_agent_profile(self, agent_id: str, allowed_tools: list[str]) -> list[str]:
        """Validate an agent's tool list against least-privilege rules.

        Returns a list of warning strings. Empty list means the profile is valid.
        Does NOT raise -- callers decide whether warnings are blocking.
        """
        warnings: list[str] = []
        profile = self._agent_profiles.get(agent_id)

        if not profile:
            warnings.append(f"No profile for agent '{agent_id}', cannot validate least-privilege")
            return warnings

        if len(allowed_tools) > profile.max_tools:
            warnings.append(
                f"Agent '{agent_id}' has {len(allowed_tools)} tools, "
                f"max is {profile.max_tools} (least-privilege violation)"
            )

        for tool in allowed_tools:
            if tool in profile.denied_tools:
                warnings.append(
                    f"Agent '{agent_id}' is denied tool '{tool}' but it's in allowed list"
                )

        return warnings

    def is_tool_allowed(self, agent_id: str, tool_name: str) -> bool:
        """Check if a tool is allowed for an agent.

        No profile for the agent -> False (ADR-015: default-deny, RC-007 fix).
        Denied list takes priority over allowed list.
        """
        profile = self._agent_profiles.get(agent_id)
        if not profile:
            return False  # ADR-015: default-deny for unknown agents

        # Harde denylist eerst: denied_actions (D5, leidend) en denied_tools (legacy-alias).
        # De unie is verboden, zodat een bestaand profiel niet losser wordt doordat iemand
        # alleen het nieuwe veld invult.
        if tool_name in profile.denied_actions or tool_name in profile.denied_tools:
            return False

        return tool_name in profile.allowed_tools

    def is_denied(self, agent_id: str, tool_name: str) -> bool:
        """Staat deze tool op de harde denylist van dit agent-profiel?

        Alleen de denylist -- expres NIET de allowlist of de default-deny. Die twee horen bij
        `is_tool_allowed()` en worden door `ToolBrokerService.execute_tool` gedaan.

        Bestaat om ADR-036 D5 op aanroeperniveau te kunnen handhaven: een "nooit
        aanraken"-actie moet geweigerd worden VOORDAT de Council er iets van kan vinden,
        anders kan een menselijke goedkeuring hem alsnog doorlaten. Een aanroeper die daarvoor
        `is_tool_allowed()` zou gebruiken, importeert ook de default-deny en weigert dan
        alles voor elke agent zonder profiel -- een veel bredere gedragswijziging dan D5
        vraagt (BE-AGT-042).

        Onbekend profiel -> False: er is dan geen denylist. De default-deny volgt alsnog in
        execute_tool, dus dit maakt niets losser.
        """
        profile = self._agent_profiles.get(agent_id)
        if not profile:
            return False
        return tool_name in profile.denied_actions or tool_name in profile.denied_tools

    def get_allowed_tools(self, agent_id: str) -> list[str]:
        """Return list of allowed tools for an agent (least privilege per ADR-015).

        Filters out any tools present on the hard denylist (denied_actions and denied_tools, ADR-036 D5).
        Returns empty list if agent has no profile (default-deny).
        """
        profile = self._agent_profiles.get(agent_id)
        if not profile:
            return []
        return [tool for tool in profile.allowed_tools if not self.is_denied(agent_id, tool)]

    def get_excessive_tools_report(self) -> dict[str, list[str]]:
        """Return agents whose allowed_tools count exceeds their max_tools limit.

        Used by validate_tool_permissions.py for least-privilege audit reports.
        """
        report: dict[str, list[str]] = {}
        for agent_id, profile in self._agent_profiles.items():
            if len(profile.allowed_tools) > profile.max_tools:
                report[agent_id] = [
                    f"Has {len(profile.allowed_tools)} tools, max is {profile.max_tools}"
                ]
        return report
