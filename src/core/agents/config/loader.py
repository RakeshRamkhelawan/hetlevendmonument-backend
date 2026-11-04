"""Configuration loader with three-tier caching."""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from .models import AgentConfig
from .validator import ConfigValidator

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with metadata."""

    config: AgentConfig
    file_hash: str
    loaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0

    def is_stale(self, max_age_seconds: int) -> bool:
        """Check if cache entry is stale."""
        age = (datetime.now(timezone.utc) - self.loaded_at).total_seconds()
        return age > max_age_seconds


class ConfigLoader:
    """
    Load and cache agent configurations from YAML files.

    Features:
    - Three-tier caching (memory, Redis, file)
    - File change detection with content hashing
    - Prompt validation integrated
    - Periodic cache refresh
    """

    def __init__(
        self,
        config_dir: str = "config/agents",
        redis_client: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        enable_caching: bool = True,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self.config_dir = Path(config_dir)
        self.redis = redis_client
        self.enable_caching = enable_caching
        self.cache_ttl = cache_ttl_seconds

        self._memory_cache: dict[str, CacheEntry] = {}
        self._cache_hashes: dict[str, str] = {}
        self._validator = ConfigValidator()

    def _get_cache_key(self, agent_name: str) -> str:
        """Generate cache key for agent."""
        return f"agent:config:{agent_name.lower()}"

    def _get_file_hash(self, filepath: Path) -> str:
        """Get file content hash for change detection."""
        try:
            return hashlib.sha256(filepath.read_bytes()).hexdigest()
        except Exception as e:
            logger.error(f"Error hashing file {filepath}: {e}")
            return ""

    def _to_snake_case(self, name: str) -> str:
        """Convert CamelCase/PascalCase to snake_case."""
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1)
        return s2.lower().replace("__", "_")

    def _get_config_path(self, agent_name: str) -> Path:
        """Resolve the on-disk YAML path for an agent config.

        Supports the current `python_pro_agent.yaml` naming convention and the
        older duplicated `_agent_agent.yaml` fallback if present.
        """
        snake_name = self._to_snake_case(agent_name)
        candidates = [
            self.config_dir / f"{snake_name}.yaml",
            self.config_dir / f"{snake_name}_agent.yaml",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return candidates[0]

    def _get_from_memory(self, cache_key: str) -> AgentConfig | None:
        """Get config from memory cache if valid."""
        if not self.enable_caching:
            return None

        entry = self._memory_cache.get(cache_key)
        if not entry:
            return None

        # Check TTL
        if entry.is_stale(self.cache_ttl):
            logger.debug(f"Memory cache stale for {cache_key}")
            del self._memory_cache[cache_key]
            return None

        entry.access_count += 1
        return entry.config

    def _get_from_redis(self, cache_key: str) -> AgentConfig | None:
        """Get config from Redis cache."""
        if not self.enable_caching or not self.redis:
            return None

        try:
            data = self.redis.get(cache_key)
            if data:
                import json

                return AgentConfig(**json.loads(data))
        except Exception as e:
            logger.error(f"Redis get error: {e}")

        return None

    def _set_memory_cache(self, cache_key: str, config: AgentConfig, file_hash: str) -> None:
        """Store config in memory cache."""
        if self.enable_caching:
            self._memory_cache[cache_key] = CacheEntry(config=config, file_hash=file_hash)

    def _set_redis_cache(self, cache_key: str, config: AgentConfig) -> None:
        """Store config in Redis cache."""
        if self.enable_caching and self.redis:
            try:
                import json

                self.redis.setex(cache_key, self.cache_ttl, json.dumps(config.dict()))
            except Exception as e:
                logger.error(f"Redis set error: {e}")

    def invalidate_cache(self, agent_name: str) -> None:
        """Invalidate all caches for an agent."""
        cache_key = self._get_cache_key(agent_name)

        if cache_key in self._memory_cache:
            del self._memory_cache[cache_key]

        if agent_name in self._cache_hashes:
            del self._cache_hashes[agent_name]

        if self.redis:
            try:
                self.redis.delete(cache_key)
            except Exception as e:
                logger.error(f"Redis delete error: {e}")

    def load(
        self,
        agent_name: str,
        use_cache: bool = True,
        check_file_changes: bool = True,
    ) -> AgentConfig | None:
        """
        Load agent configuration with caching.

        Args:
            agent_name: Agent name (e.g., "PythonProAgent")
            use_cache: Whether to use caching
            check_file_changes: Whether to check if file changed on disk

        Returns:
            AgentConfig or None if not found/invalid
        """
        cache_key = self._get_cache_key(agent_name)

        yaml_file = self._get_config_path(agent_name)

        # Check memory cache with file change detection
        if use_cache:
            cached = self._get_from_memory(cache_key)
            if cached and check_file_changes:
                current_hash = self._get_file_hash(yaml_file)
                cached_hash = self._cache_hashes.get(agent_name)

                if cached_hash and current_hash == cached_hash:
                    logger.debug(f"Memory cache hit for {agent_name}")
                    return cached
                else:
                    logger.info(f"File changed for {agent_name}, invalidating cache")
                    self.invalidate_cache(agent_name)
            elif cached:
                return cached

        # Check Redis cache
        if use_cache:
            cached = self._get_from_redis(cache_key)
            if cached:
                logger.debug(f"Redis cache hit for {agent_name}")
                self._set_memory_cache(cache_key, cached, "")
                return cached

        # Load from file
        if not yaml_file.exists():
            logger.debug(f"Config file not found: {yaml_file}")
            return None

        result = self._validator.validate_file(str(yaml_file))

        if not result.is_valid:
            logger.error(f"Config validation failed for {agent_name}: {result.errors}")
            return None

        config = result.config
        if config is None:
            logger.debug(f"Config is None for {agent_name}")
            return None

        file_hash = self._get_file_hash(yaml_file)

        # Cache it
        if use_cache:
            self._set_memory_cache(cache_key, config, file_hash)
            self._set_redis_cache(cache_key, config)
            self._cache_hashes[agent_name] = file_hash

        return config

    def reload(self, agent_name: str) -> AgentConfig | None:
        """Force reload agent configuration from disk."""
        self.invalidate_cache(agent_name)
        return self.load(agent_name, use_cache=False)

    def load_all(self) -> dict[str, AgentConfig]:
        """Load all agent configurations."""
        configs: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for yaml_file in self.config_dir.glob("*.yaml"):
            if yaml_file.name.startswith("_"):
                continue

            # Extract agent name from filename
            agent_file_name = yaml_file.stem.replace("_agent", "")
            # Convert to CamelCase
            parts = agent_file_name.split("_")
            camel_name = "".join(p.capitalize() for p in parts if p) + "Agent"

            config = self.load(camel_name, use_cache=False)
            if config:
                configs[config.agent.name] = config

        return configs

    def check_for_changes(self) -> dict[str, bool]:
        """Check which configs have changed on disk.

        Returns: Dict[str, Any]ionary mapping agent names to changed status  # TODO(TYPE): replace Any with concrete type
        """
        changes: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for yaml_file in self.config_dir.glob("*.yaml"):
            if yaml_file.name.startswith("_"):
                continue

            agent_file_name = yaml_file.stem.replace("_agent", "")
            parts = agent_file_name.split("_")
            camel_name = "".join(p.capitalize() for p in parts if p) + "Agent"

            current_hash = self._get_file_hash(yaml_file)
            cached_hash = self._cache_hashes.get(camel_name)

            changes[camel_name] = cached_hash != current_hash

        return changes

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get loader statistics."""
        return {
            "config_dir": str(self.config_dir),
            "caching_enabled": self.enable_caching,
            "cache_ttl_seconds": self.cache_ttl,
            "memory_cache_size": len(self._memory_cache),
            "redis_available": self.redis is not None,
        }


# Singleton loader instance
_loader_instance: ConfigLoader | None = None


def get_config_loader(
    config_dir: str = "config/agents",
    redis_client: Any | None = None,  # TODO(TYPE): replace Any with concrete type
) -> ConfigLoader:
    """Get or create singleton ConfigLoader instance."""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = ConfigLoader(config_dir=config_dir, redis_client=redis_client)
    return _loader_instance


def reset_config_loader() -> None:
    """Reset singleton instance (for testing)."""
    global _loader_instance
    _loader_instance = None
