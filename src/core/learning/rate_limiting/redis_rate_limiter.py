"""
RedisRateLimiter -- Gedistribueerde rate limiting voor twin observaties.

Gebruikt Redis sliding window per user+behavior_type combo.
Fail-open: als Redis niet beschikbaar is, wordt de observatie toegelaten
(beter data verliezen dan de hoofd-app blokkeren).

Gebruik:
    limiter = RedisRateLimiter(redis_client=my_redis)
    allowed = await limiter.is_allowed(user_id="u1", behavior_type="file_edit")

Voor unit tests zonder Redis:
    limiter = RedisRateLimiter(redis_client=None)  # altijd allowed
"""

import time
import uuid
from typing import Any, Optional

from loguru import logger

# Limieten: behavior_type -> (max_count, window_seconds)
_DEFAULT_LIMITS: dict[str, tuple[int, int]] = {
    "repeated_edits_same_line": (10, 60),
    "copy_paste": (50, 60),
    "work_start": (5, 3600),
    "undo_loop": (20, 60),
    "rapid_switch": (30, 60),
    "default": (100, 60),
}


class RedisRateLimiter:
    """
    Sliding-window rate limiter backed by Redis.

    Redis-key format: twin:rl:{user_id}:{behavior_type}
    Waarde: sorted set van timestamps (score = timestamp, member = timestamp)
    """

    def __init__(
        self,
        redis_client: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        limits: dict[str, tuple[int, int]] | None = None,
    ):
        self._redis = redis_client
        self._limits = limits or _DEFAULT_LIMITS

    async def is_allowed(self, user_id: str, behavior_type: str) -> bool:
        """
        Controleer of een observatie is toegestaan.

        Returns:
            True als toegestaan (of als Redis niet beschikbaar is).
            False als rate limit overschreden.
        """
        if self._redis is None:
            # Geen Redis: altijd toegestaan (test mode / Redis down)
            return True

        max_count, window_seconds = self._get_limit(behavior_type)
        key = f"twin:rl:{user_id}:{behavior_type}"
        now = time.time()
        window_start = now - window_seconds

        try:
            pipe = self._redis.pipeline()
            # Verwijder verouderde entries
            pipe.zremrangebyscore(key, 0, window_start)
            # Tel huidige entries
            pipe.zcard(key)
            # Voeg huidige timestamp toe. Het LID moet uniek zijn, niet alleen de score --
            # `time.time()` geeft op deze machine bij twee snel opeenvolgende aanroepen
            # empirisch (1000/1000) DEZELFDE waarde terug. Een member gelijk aan `str(now)`
            # zou dan de vorige entry in de sorted set overschrijven i.p.v. een nieuwe toe te
            # voegen, en de teller zou stil te laag blijven -- precies bij de belasting
            # (snelle, opeenvolgende requests) waar deze rate limiter tegen moet beschermen.
            pipe.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
            # Stel expiratie in op window_seconds + buffer
            pipe.expire(key, window_seconds + 10)
            results = await pipe.execute()

            current_count = results[1]  # zcard resultaat

            if current_count >= max_count:
                logger.debug(
                    "rate_limit_hit",
                    user_id=user_id,
                    behavior_type=behavior_type,
                    current_count=current_count,
                    max_count=max_count,
                )
                return False

            return True

        except Exception as exc:
            # Fail-open: als Redis faalt, laat de observatie door
            logger.warning(
                "rate_limiter_redis_error",
                user_id=user_id,
                behavior_type=behavior_type,
                error=str(exc),
            )
            return True

    def _get_limit(self, behavior_type: str) -> tuple[int, int]:
        """Geef de rate limit voor een bepaald behavior type."""
        return self._limits.get(behavior_type, self._limits["default"])
