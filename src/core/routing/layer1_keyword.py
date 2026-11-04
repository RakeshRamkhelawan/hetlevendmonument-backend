import logging
import re
from typing import Optional

from src.core.shared.interfaces import TaskData

logger = logging.getLogger(__name__)


class KeywordRouter:
    """
    Layer 1 (Tamas): High-speed deterministic routing based on keywords and regex.
    Target latency: <10ms.
    """

    # Mapping of keywords to supervisor IDs
    KEYWORDS = {
        r"\b(invoice|payment|tax|salary|finance|payroll)\b": "finance_supervisor",
        r"\b(hire|hiring|candidate|employee|hr|leave)\b": "hr_supervisor",
        r"\b(security|threat|firewall|incident|attack)\b": "it_security_supervisor",
        r"\b(legal|contract|gdpr|compliance)\b": "legal_supervisor",
        r"\b(status|health|uptime)\b": "operations_supervisor",
    }

    def route(self, task: TaskData) -> str | None:
        """
        Check if any keyword matches the task description or title.
        """
        content = f"{task.title} {task.description} {task.metadata.get('text', '')}".lower()

        for pattern, target in self.KEYWORDS.items():
            if re.search(pattern, content):
                logger.debug(f"Layer 1 Match: '{pattern}' -> {target}")
                return target

        return None
