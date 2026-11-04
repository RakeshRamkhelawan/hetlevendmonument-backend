"""
Notification Preference Models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

DeliveryMode = Literal["individual", "batched", "digest"]


@dataclass(frozen=True, slots=True)
class NotificationPreferences:
    user_id: int
    tenant_id: int
    daily_limit: int = 25
    delivery_mode: DeliveryMode = "individual"
    critical_always_immediate: bool = True
    quiet_hours_start: int | None = None
    quiet_hours_end: int | None = None
    quiet_hours_timezone: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.daily_limit <= 100:
            raise ValueError("daily_limit must be 0..100")
        if self.tenant_id <= 0 or self.user_id <= 0:
            raise ValueError("user_id and tenant_id must be > 0")
        if (self.quiet_hours_start is None) != (self.quiet_hours_end is None):
            raise ValueError("quiet_hours_start and quiet_hours_end must both be set or both null")
        if self.quiet_hours_start is not None and not 0 <= self.quiet_hours_start <= 23:
            raise ValueError("quiet_hours_start must be 0..23")
        if self.quiet_hours_end is not None and not 0 <= self.quiet_hours_end <= 23:
            raise ValueError("quiet_hours_end must be 0..23")
