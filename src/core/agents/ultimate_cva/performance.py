import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import CVAMode, ParsedCommand

logger = logging.getLogger("UltimateCVA.Performance")


def analyze_performance(
    performance_cache: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    result: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    execution_time: float,
    parsed_command: ParsedCommand,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Analyze and update performance cache (returns updated cache)"""
    perf_key = f"{parsed_command.intent.value}_{int(parsed_command.confidence * 10)}"

    if perf_key not in performance_cache:
        performance_cache[perf_key] = []

    performance_cache[perf_key].append(
        {
            "execution_time": execution_time,
            "success": result.get("success", False),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "llm_provider": result.get("llm_provider", "unknown"),
        }
    )

    # Keep only recent performance data
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    performance_cache[perf_key] = [
        entry
        for entry in performance_cache[perf_key]
        if datetime.fromisoformat(entry["timestamp"]) > cutoff
    ]

    return performance_cache


def load_performance_cache() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Load performance cache from file"""
    try:
        cache_file = Path("logs/ultimate_cva_cache.json")
        if cache_file.exists():
            with open(cache_file) as f:
                cache_data: dict[str, Any] = json.load(f)  # TODO(TYPE): replace Any with concrete type
            logger.info(f"Loaded Ultimate CVA performance cache with {len(cache_data)} entries")
            return cache_data
    except Exception as e:
        logger.warning(f"Could not load performance cache: {e}")
    return {}


def get_performance_metrics(
    execution_history: list[Any],  # TODO(TYPE): replace Any with concrete type
    context_memory: list[Any],  # TODO(TYPE): replace Any with concrete type
    performance_cache: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    last_optimization: datetime,
    cva_mode: CVAMode,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get current performance metrics"""
    return {
        "execution_history_size": len(execution_history),
        "context_memory_size": len(context_memory),
        "performance_cache_size": len(performance_cache),
        "last_optimization": last_optimization.isoformat(),
        "llm_integration_active": True,
        "ceo_mode_active": cva_mode == CVAMode.CEO_MODE,
    }
