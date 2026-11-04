"""Cookie/data consent categories -- shared layer, no governance deps."""

from __future__ import annotations

from enum import Enum


class ConsentCategory(str, Enum):
    """Consent categories for cookie and data processing consent."""

    ESSENTIAL = "essential"
    ANALYTICS = "analytics"
    MARKETING = "marketing"
    PERSONALIZATION = "personalization"
