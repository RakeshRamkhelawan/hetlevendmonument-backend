"""
System Tuner - Dynamic system configuration and parameter tuning
Optimizes system parameters and configurations for optimal performance
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.caching.cache_layer import get_cache_manager
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)


class TuningStrategy(Enum):
    """System tuning strategies"""

    PERFORMANCE_FOCUSED = "performance_focused"
    RESOURCE_EFFICIENT = "resource_efficient"
    BALANCED = "balanced"
    STABILITY_FOCUSED = "stability_focused"
    CUSTOM = "custom"


class ConfigurationCategory(Enum):
    """Categories of system configuration"""

    RUNTIME_SETTINGS = "runtime_settings"
    MEMORY_MANAGEMENT = "memory_management"
    CONCURRENCY_SETTINGS = "concurrency_settings"
    CACHE_CONFIGURATION = "cache_configuration"
    DATABASE_SETTINGS = "database_settings"
    NETWORK_SETTINGS = "network_settings"
    LOGGING_SETTINGS = "logging_settings"


@dataclass
class TuningConfiguration:
    """System tuning configuration"""

    config_id: str
    category: ConfigurationCategory
    parameters: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    strategy: TuningStrategy
    expected_impact: str
    risk_level: str
    validation_rules: list[str] = field(default_factory=list)
    rollback_config: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    applied_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary"""
        return {
            "config_id": self.config_id,
            "category": self.category.value,
            "parameters": self.parameters,
            "strategy": self.strategy.value,
            "expected_impact": self.expected_impact,
            "risk_level": self.risk_level,
            "validation_rules": self.validation_rules,
            "rollback_config": self.rollback_config,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
        }


class ConfigurationValidator:
    """Validates configuration changes before applying"""

    def __init__(self) -> None:
        self.validation_rules = {
            ConfigurationCategory.MEMORY_MANAGEMENT: self._validate_memory_config,
            ConfigurationCategory.CONCURRENCY_SETTINGS: self._validate_concurrency_config,
            ConfigurationCategory.CACHE_CONFIGURATION: self._validate_cache_config,
            ConfigurationCategory.DATABASE_SETTINGS: self._validate_database_config,
            ConfigurationCategory.NETWORK_SETTINGS: self._validate_network_config,
        }

    async def validate_configuration(self, config: TuningConfiguration) -> tuple[bool, list[str]]:
        """Validate configuration before applying"""
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        try:
            # Category-specific validation
            if config.category in self.validation_rules:
                validator = self.validation_rules[config.category]
                category_errors = await validator(config.parameters)
                errors.extend(category_errors)

            # General validation rules
            general_errors = await self._validate_general_rules(config)
            errors.extend(general_errors)

            # Custom validation rules
            for rule in config.validation_rules:
                rule_errors = await self._validate_custom_rule(rule, config.parameters)
                errors.extend(rule_errors)

            is_valid = len(errors) == 0
            return is_valid, errors

        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            return False, [f"Validation error: {str(e)}"]

    async def _validate_memory_config(self, parameters: dict[str, Any]) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Validate memory configuration parameters"""
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if "max_memory_mb" in parameters:
            max_memory = parameters["max_memory_mb"]
            if not isinstance(max_memory, (int, float)) or max_memory <= 0:
                errors.append("max_memory_mb must be a positive number")
            elif max_memory > 32768:  # 32GB limit
                errors.append("max_memory_mb exceeds reasonable limit (32GB)")

        if "gc_threshold" in parameters:
            gc_threshold = parameters["gc_threshold"]
            if not isinstance(gc_threshold, (int, float)) or gc_threshold < 0 or gc_threshold > 1:
                errors.append("gc_threshold must be between 0 and 1")

        return errors

    async def _validate_concurrency_config(self, parameters: dict[str, Any]) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Validate concurrency configuration parameters"""
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if "max_workers" in parameters:
            max_workers = parameters["max_workers"]
            if not isinstance(max_workers, int) or max_workers <= 0:
                errors.append("max_workers must be a positive integer")
            elif max_workers > 1000:
                errors.append("max_workers exceeds reasonable limit (1000)")

        if "thread_pool_size" in parameters:
            pool_size = parameters["thread_pool_size"]
            if not isinstance(pool_size, int) or pool_size <= 0:
                errors.append("thread_pool_size must be a positive integer")

        return errors

    async def _validate_cache_config(self, parameters: dict[str, Any]) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Validate cache configuration parameters"""
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if "cache_size_mb" in parameters:
            cache_size = parameters["cache_size_mb"]
            if not isinstance(cache_size, (int, float)) or cache_size <= 0:
                errors.append("cache_size_mb must be a positive number")

        if "ttl_seconds" in parameters:
            ttl = parameters["ttl_seconds"]
            if not isinstance(ttl, int) or ttl <= 0:
                errors.append("ttl_seconds must be a positive integer")

        return errors

    async def _validate_database_config(self, parameters: dict[str, Any]) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Validate database configuration parameters"""
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if "connection_pool_size" in parameters:
            pool_size = parameters["connection_pool_size"]
            if not isinstance(pool_size, int) or pool_size <= 0:
                errors.append("connection_pool_size must be a positive integer")
            elif pool_size > 100:
                errors.append("connection_pool_size exceeds reasonable limit (100)")

        if "query_timeout_seconds" in parameters:
            timeout = parameters["query_timeout_seconds"]
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                errors.append("query_timeout_seconds must be a positive number")

        return errors

    async def _validate_network_config(self, parameters: dict[str, Any]) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Validate network configuration parameters"""
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if "request_timeout_seconds" in parameters:
            timeout = parameters["request_timeout_seconds"]
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                errors.append("request_timeout_seconds must be a positive number")

        if "max_connections" in parameters:
            max_conn = parameters["max_connections"]
            if not isinstance(max_conn, int) or max_conn <= 0:
                errors.append("max_connections must be a positive integer")

        return errors

    async def _validate_general_rules(self, config: TuningConfiguration) -> list[str]:
        """Validate general configuration rules"""
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check if parameters dict is valid
        if not isinstance(config.parameters, dict):
            errors.append("Parameters must be a dictionary")

        # Check if configuration has any parameters
        if not config.parameters:
            errors.append("Configuration must have at least one parameter")

        # Validate risk level
        valid_risk_levels = ["low", "medium", "high"]
        if config.risk_level not in valid_risk_levels:
            errors.append(f"Risk level must be one of: {valid_risk_levels}")

        return errors

    async def _validate_custom_rule(self, rule: str, parameters: dict[str, Any]) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Validate custom validation rule"""
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        try:
            # Simple rule evaluation (in production, use more sophisticated rule engine)
            if rule.startswith("min_value:"):
                _, param_name, min_val = rule.split(":")
                if param_name in parameters:
                    if parameters[param_name] < float(min_val):
                        errors.append(f"{param_name} must be at least {min_val}")

            elif rule.startswith("max_value:"):
                _, param_name, max_val = rule.split(":")
                if param_name in parameters:
                    if parameters[param_name] > float(max_val):
                        errors.append(f"{param_name} must not exceed {max_val}")

        except Exception as e:
            logger.warning(f"Custom rule validation failed: {e}")

        return errors


class ConfigurationApplier:
    """Applies validated configurations to the system"""

    def __init__(self) -> None:
        self.applied_configurations: dict[str, TuningConfiguration] = {}
        self.configuration_backup: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    async def apply_configuration(self, config: TuningConfiguration) -> bool:
        """Apply configuration to the system"""
        try:
            logger.info(f"Applying configuration: {config.config_id}")

            # Backup current configuration
            await self._backup_current_config(config)

            # Apply configuration based on category
            success = await self._apply_category_config(config)

            if success:
                config.applied_at = datetime.now(timezone.utc)
                self.applied_configurations[config.config_id] = config
                logger.info(f"Configuration applied successfully: {config.config_id}")
            else:
                logger.error(f"Configuration application failed: {config.config_id}")

            return success

        except Exception as e:
            logger.error(f"Configuration application error: {e}")
            return False

    async def rollback_configuration(self, config_id: str) -> bool:
        """Rollback a previously applied configuration"""
        try:
            if config_id not in self.applied_configurations:
                logger.warning(f"Configuration not found for rollback: {config_id}")
                return False

            config = self.applied_configurations[config_id]

            if config.rollback_config:
                # Apply rollback configuration
                rollback_success = await self._apply_parameters(
                    config.category, config.rollback_config
                )

                if rollback_success:
                    del self.applied_configurations[config_id]
                    logger.info(f"Configuration rolled back successfully: {config_id}")
                    return True

            logger.error(f"Configuration rollback failed: {config_id}")
            return False

        except Exception as e:
            logger.error(f"Configuration rollback error: {e}")
            return False

    async def _backup_current_config(self, config: TuningConfiguration) -> None:
        """Backup current configuration before applying changes"""
        try:
            current_config = await self._get_current_config(config.category)
            self.configuration_backup[config.config_id] = current_config
            config.rollback_config = current_config

        except Exception as e:
            logger.warning(f"Configuration backup failed: {e}")

    async def _get_current_config(self, category: ConfigurationCategory) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current system configuration for category"""
        current_config: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        try:
            if category == ConfigurationCategory.RUNTIME_SETTINGS:
                current_config = {
                    "debug_mode": logger.logger.level <= 10,  # DEBUG level
                    "async_mode": True,
                }

            elif category == ConfigurationCategory.MEMORY_MANAGEMENT:
                current_config = {
                    "max_memory_mb": 1024,
                    "gc_threshold": 0.7,
                }  # Default values

            elif category == ConfigurationCategory.CONCURRENCY_SETTINGS:
                current_config = {"max_workers": 10, "thread_pool_size": 4}

            elif category == ConfigurationCategory.CACHE_CONFIGURATION:
                await get_cache_manager().get_stats()
                current_config = {
                    "cache_enabled": True,
                    "cache_size_mb": 100,
                    "ttl_seconds": 300,
                }

        except Exception as e:
            logger.warning(f"Failed to get current config for {category.value}: {e}")

        return current_config

    async def _apply_category_config(self, config: TuningConfiguration) -> bool:
        """Apply configuration based on category"""
        try:
            return await self._apply_parameters(config.category, config.parameters)
        except Exception as e:
            logger.error(f"Category configuration application failed: {e}")
            return False

    async def _apply_parameters(
        self, category: ConfigurationCategory, parameters: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """Apply parameters for specific category"""
        try:
            if category == ConfigurationCategory.RUNTIME_SETTINGS:
                return await self._apply_runtime_settings(parameters)

            elif category == ConfigurationCategory.MEMORY_MANAGEMENT:
                return await self._apply_memory_settings(parameters)

            elif category == ConfigurationCategory.CONCURRENCY_SETTINGS:
                return await self._apply_concurrency_settings(parameters)

            elif category == ConfigurationCategory.CACHE_CONFIGURATION:
                return await self._apply_cache_settings(parameters)

            elif category == ConfigurationCategory.DATABASE_SETTINGS:
                return await self._apply_database_settings(parameters)

            elif category == ConfigurationCategory.NETWORK_SETTINGS:
                return await self._apply_network_settings(parameters)

            elif category == ConfigurationCategory.LOGGING_SETTINGS:
                return await self._apply_logging_settings(parameters)

            else:
                logger.warning(f"Unknown configuration category: {category.value}")
                return False

        except Exception as e:
            logger.error(f"Parameter application failed for {category.value}: {e}")
            return False

    async def _apply_runtime_settings(self, parameters: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Apply runtime settings"""
        try:
            if "debug_mode" in parameters:
                debug_mode = parameters["debug_mode"]
                # In production, this would set actual debug mode
                logger.info(f"Debug mode set to: {debug_mode}")

            if "async_mode" in parameters:
                async_mode = parameters["async_mode"]
                logger.info(f"Async mode set to: {async_mode}")

            return True
        except Exception as e:
            logger.error(f"Runtime settings application failed: {e}")
            return False

    async def _apply_memory_settings(self, parameters: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Apply memory management settings"""
        try:
            if "max_memory_mb" in parameters:
                max_memory = parameters["max_memory_mb"]
                # In production, this would set actual memory limits
                logger.info(f"Max memory set to: {max_memory}MB")

            if "gc_threshold" in parameters:
                gc_threshold = parameters["gc_threshold"]
                # In production, this would configure garbage collection
                logger.info(f"GC threshold set to: {gc_threshold}")

            return True
        except Exception as e:
            logger.error(f"Memory settings application failed: {e}")
            return False

    async def _apply_concurrency_settings(self, parameters: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Apply concurrency settings"""
        try:
            if "max_workers" in parameters:
                max_workers = parameters["max_workers"]
                # In production, this would configure thread/process pools
                logger.info(f"Max workers set to: {max_workers}")

            if "thread_pool_size" in parameters:
                pool_size = parameters["thread_pool_size"]
                logger.info(f"Thread pool size set to: {pool_size}")

            return True
        except Exception as e:
            logger.error(f"Concurrency settings application failed: {e}")
            return False

    async def _apply_cache_settings(self, parameters: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Apply cache settings"""
        try:
            if "cache_size_mb" in parameters:
                cache_size = parameters["cache_size_mb"]
                logger.info(f"Cache size set to: {cache_size}MB")

            if "ttl_seconds" in parameters:
                ttl = parameters["ttl_seconds"]
                logger.info(f"Default TTL set to: {ttl}s")

            return True
        except Exception as e:
            logger.error(f"Cache settings application failed: {e}")
            return False

    async def _apply_database_settings(self, parameters: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Apply database settings"""
        try:
            if "connection_pool_size" in parameters:
                pool_size = parameters["connection_pool_size"]
                logger.info(f"DB connection pool size set to: {pool_size}")

            if "query_timeout_seconds" in parameters:
                timeout = parameters["query_timeout_seconds"]
                logger.info(f"DB query timeout set to: {timeout}s")

            return True
        except Exception as e:
            logger.error(f"Database settings application failed: {e}")
            return False

    async def _apply_network_settings(self, parameters: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Apply network settings"""
        try:
            if "request_timeout_seconds" in parameters:
                timeout = parameters["request_timeout_seconds"]
                logger.info(f"Request timeout set to: {timeout}s")

            if "max_connections" in parameters:
                max_conn = parameters["max_connections"]
                logger.info(f"Max connections set to: {max_conn}")

            return True
        except Exception as e:
            logger.error(f"Network settings application failed: {e}")
            return False

    async def _apply_logging_settings(self, parameters: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Apply logging settings"""
        try:
            if "log_level" in parameters:
                log_level = parameters["log_level"]
                logger.info(f"Log level set to: {log_level}")

            if "log_format" in parameters:
                log_format = parameters["log_format"]
                logger.info(f"Log format set to: {log_format}")

            return True
        except Exception as e:
            logger.error(f"Logging settings application failed: {e}")
            return False


class SystemTuner:
    """
    Main system tuner that coordinates configuration management and optimization
    """

    def __init__(self) -> None:
        self.validator = ConfigurationValidator()
        self.applier = ConfigurationApplier()
        self.tuning_configurations: dict[str, TuningConfiguration] = {}
        self._initialized = False
        self._stats = {
            "configurations_applied": 0,
            "configurations_rolled_back": 0,
            "validation_failures": 0,
        }

    async def initialize(self) -> bool:
        """Initialize system tuner"""
        try:
            # Load default tuning configurations
            await self._load_default_configurations()

            self._initialized = True
            logger.info("System Tuner initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize system tuner: {e}")
            return False

    async def create_tuning_configuration(
        self,
        category: ConfigurationCategory,
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        strategy: TuningStrategy = TuningStrategy.BALANCED,
        risk_level: str = "medium",
    ) -> TuningConfiguration:
        """Create a new tuning configuration"""
        config_id = f"tune_{category.value}_{int(datetime.now(timezone.utc).timestamp())}"

        config = TuningConfiguration(
            config_id=config_id,
            category=category,
            parameters=parameters,
            strategy=strategy,
            expected_impact=self._estimate_impact(category, parameters),
            risk_level=risk_level,
        )

        self.tuning_configurations[config_id] = config
        return config

    async def apply_tuning_configuration(
        self, config: TuningConfiguration
    ) -> tuple[bool, list[str]]:
        """Apply tuning configuration with validation"""
        try:
            # Validate configuration
            is_valid, validation_errors = await self.validator.validate_configuration(config)

            if not is_valid:
                self._stats["validation_failures"] += 1
                logger.warning(f"Configuration validation failed: {config.config_id}")
                return False, validation_errors

            # Apply configuration
            success = await self.applier.apply_configuration(config)

            if success:
                self._stats["configurations_applied"] += 1
                logger.info(f"Configuration applied successfully: {config.config_id}")
                return True, []
            else:
                return False, ["Configuration application failed"]

        except Exception as e:
            logger.error(f"Configuration application error: {e}")
            return False, [f"Application error: {str(e)}"]

    async def rollback_configuration(self, config_id: str) -> bool:
        """Rollback a configuration"""
        try:
            success = await self.applier.rollback_configuration(config_id)

            if success:
                self._stats["configurations_rolled_back"] += 1

            return success

        except Exception as e:
            logger.error(f"Configuration rollback error: {e}")
            return False

    async def get_optimization_recommendations(
        self, system_metrics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> list[TuningConfiguration]:
        """Get optimization recommendations based on system metrics"""
        recommendations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        try:
            # Analyze system metrics and generate recommendations
            cpu_usage = system_metrics.get("cpu_usage", 0)
            memory_usage = system_metrics.get("memory_usage", 0)
            system_load = system_metrics.get("system_load", 0)

            # High CPU usage recommendations
            if cpu_usage > 80:
                recommendations.append(await self._create_cpu_optimization_config())

            # High memory usage recommendations
            if memory_usage > 85:
                recommendations.append(await self._create_memory_optimization_config())

            # High system load recommendations
            if system_load > 0.8:
                recommendations.append(await self._create_concurrency_optimization_config())

            # General performance recommendations
            recommendations.append(await self._create_cache_optimization_config())

        except Exception as e:
            logger.error(f"Recommendation generation failed: {e}")

        return recommendations

    async def get_tuning_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get system tuning statistics"""
        return {
            "configurations_applied": self._stats["configurations_applied"],
            "configurations_rolled_back": self._stats["configurations_rolled_back"],
            "validation_failures": self._stats["validation_failures"],
            "active_configurations": len(self.applier.applied_configurations),
            "available_configurations": len(self.tuning_configurations),
        }

    async def _load_default_configurations(self) -> None:
        """Load default tuning configurations"""
        try:
            # Performance-focused configurations
            await self.create_tuning_configuration(
                category=ConfigurationCategory.CONCURRENCY_SETTINGS,
                parameters={"max_workers": 20, "thread_pool_size": 8},
                strategy=TuningStrategy.PERFORMANCE_FOCUSED,
                risk_level="medium",
            )

            # Resource-efficient configurations
            await self.create_tuning_configuration(
                category=ConfigurationCategory.MEMORY_MANAGEMENT,
                parameters={"max_memory_mb": 512, "gc_threshold": 0.8},
                strategy=TuningStrategy.RESOURCE_EFFICIENT,
                risk_level="low",
            )

            logger.info("Default tuning configurations loaded")

        except Exception as e:
            logger.warning(f"Failed to load default configurations: {e}")

    def _estimate_impact(self, category: ConfigurationCategory, parameters: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Estimate the expected impact of configuration changes"""
        try:
            param_count = len(parameters)

            if category in [
                ConfigurationCategory.CONCURRENCY_SETTINGS,
                ConfigurationCategory.MEMORY_MANAGEMENT,
            ]:
                return "high" if param_count >= 3 else "medium"
            elif category in [
                ConfigurationCategory.CACHE_CONFIGURATION,
                ConfigurationCategory.NETWORK_SETTINGS,
            ]:
                return "medium" if param_count >= 2 else "low"
            else:
                return "low"

        except Exception:
            return "unknown"

    async def _create_cpu_optimization_config(self) -> TuningConfiguration:
        """Create CPU optimization configuration"""
        return await self.create_tuning_configuration(
            category=ConfigurationCategory.CONCURRENCY_SETTINGS,
            parameters={"max_workers": 16, "thread_pool_size": 6},
            strategy=TuningStrategy.PERFORMANCE_FOCUSED,
            risk_level="medium",
        )

    async def _create_memory_optimization_config(self) -> TuningConfiguration:
        """Create memory optimization configuration"""
        return await self.create_tuning_configuration(
            category=ConfigurationCategory.MEMORY_MANAGEMENT,
            parameters={"max_memory_mb": 2048, "gc_threshold": 0.6},
            strategy=TuningStrategy.PERFORMANCE_FOCUSED,
            risk_level="medium",
        )

    async def _create_concurrency_optimization_config(self) -> TuningConfiguration:
        """Create concurrency optimization configuration"""
        return await self.create_tuning_configuration(
            category=ConfigurationCategory.CONCURRENCY_SETTINGS,
            parameters={"max_workers": 12, "thread_pool_size": 4},
            strategy=TuningStrategy.BALANCED,
            risk_level="low",
        )

    async def _create_cache_optimization_config(self) -> TuningConfiguration:
        """Create cache optimization configuration"""
        return await self.create_tuning_configuration(
            category=ConfigurationCategory.CACHE_CONFIGURATION,
            parameters={"cache_size_mb": 256, "ttl_seconds": 600},
            strategy=TuningStrategy.PERFORMANCE_FOCUSED,
            risk_level="low",
        )


# Global system tuner instance
_global_tuner: SystemTuner | None = None


async def get_system_tuner() -> SystemTuner:
    """Get global system tuner instance"""
    global _global_tuner

    if _global_tuner is None:
        _global_tuner = SystemTuner()
        await _global_tuner.initialize()

    return _global_tuner
