"""Tool Risk Classifier - determines risk level for tools."""

from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger

logger = logger.bind(module="risk_classifier")


class ToolRiskLevel(Enum):
    """Risk levels for tool execution."""

    LOW = "low"  # Direct execution
    MEDIUM = "medium"  # Log + post-action alert
    HIGH = "high"  # HITL required


class ToolRiskClassifier:
    """Classifies tools into risk levels based on YAML configuration.

    Resolution order:
    1. Exact match in tool_risk_levels
    2. Prefix match in tool_prefixes (for unlisted tools in a known namespace)
    3. default_risk_level (zero-trust HIGH for completely unknown tools)
    """

    DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "tool_risk_levels.yml"

    def __init__(self, config_path: str | None = None) -> None:
        self._risk_levels: dict[str, ToolRiskLevel] = {}
        self._prefix_levels: dict[str, ToolRiskLevel] = {}
        self._default_risk_level = ToolRiskLevel.HIGH
        self._required_permissions: dict[str, str] = {}
        self._load_config(config_path)

    def _load_config(self, config_path: str | None) -> None:
        """Load risk level configuration from YAML."""
        path = Path(config_path) if config_path else self.DEFAULT_CONFIG_PATH

        if not path.exists():
            logger.warning("Tool risk config not found at %s, using defaults", path)
            return

        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or not isinstance(data, dict):
                logger.warning("Empty tool risk config, using defaults")
                return

            for tool_name, risk_str in data.get("tool_risk_levels", {}).items():
                try:
                    self._risk_levels[tool_name] = ToolRiskLevel(risk_str.lower())
                except ValueError:
                    logger.warning(
                        "Unknown risk level '%s' for tool '%s', skipping",
                        risk_str,
                        tool_name,
                    )

            for prefix, risk_str in data.get("tool_prefixes", {}).items():
                try:
                    self._prefix_levels[prefix] = ToolRiskLevel(risk_str.lower())
                except ValueError:
                    logger.warning(
                        "Unknown risk level '%s' for prefix '%s', skipping",
                        risk_str,
                        prefix,
                    )

            default_str = data.get("default_risk_level", "high")
            try:
                self._default_risk_level = ToolRiskLevel(default_str.lower())
            except ValueError:
                logger.warning("Invalid default risk level '%s', using HIGH", default_str)
                self._default_risk_level = ToolRiskLevel.HIGH

            # Vereist recht per tool. De waarden worden hier NIET tegen de Permission-enum
            # gevalideerd -- dat zou een tool_broker->auth-koppeling maken. De aanroeper in
            # `auth/rbac.py` doet de vertaling en weigert bij een onbekende naam.
            for tool_name, perm in data.get("tool_required_permission", {}).items():
                if isinstance(perm, str) and perm.strip():
                    self._required_permissions[tool_name] = perm.strip().lower()
                else:
                    logger.warning(
                        "Invalid required permission %r for tool '%s', skipping -- de tool "
                        "valt daarmee op de strengste default",
                        perm,
                        tool_name,
                    )

        except yaml.YAMLError as e:
            logger.error("Failed to parse tool risk config: %s, using defaults", e)

    def classify(self, tool_name: str) -> ToolRiskLevel:
        """Classify a tool into a risk level.

        Resolution order: exact match -> prefix match -> default (HIGH).
        """
        if tool_name in self._risk_levels:
            return self._risk_levels[tool_name]

        for prefix, level in self._prefix_levels.items():
            if tool_name.startswith(prefix):
                return level

        return self._default_risk_level

    def required_permission(self, tool_name: str) -> str | None:
        """Welk recht de aanvragende MENS moet hebben om deze tool te laten draaien.

        `None` betekent: geen regel, dus GEEN mens mag hem draaien -- de aanroeper weigert.
        Bewust geen terugval op een bestaand recht: "het strengste bestaande recht" zou
        betekenen dat een beheerder elke ongeclassificeerde tool mag draaien, en dan opent een
        nieuwe tool zichzelf zolang niemand eraan denkt hem te classificeren.
        `tests/architecture/test_every_executable_tool_has_a_required_permission.py` zorgt dat
        dit nooit een echte tool raakt.

        Ook geen prefix-terugval, in tegenstelling tot `classify()`: daar geeft een prefix een
        namespace een redelijke inschatting, hier zou hij een tool ongemerkt soepeler maken
        (OP-130 liet zien dat `classify()` bovendien de EERSTE passende prefix neemt, niet de
        langste).
        """
        return self._required_permissions.get(tool_name)
