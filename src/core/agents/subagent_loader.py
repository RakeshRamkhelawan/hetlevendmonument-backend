"""
Subagent Loader - Production-Ready Dynamic Agent Discovery and Loading System
Handles dynamic loading, registration, and management of specialized subagents
ASCII-only compliance enforced - no Unicode characters
"""

import asyncio
import importlib
import importlib.util
import inspect
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING, cast
from collections.abc import Callable

if TYPE_CHECKING:
    from src.core.shared.interfaces import Agent

# Import caching for performance optimization
get_cache_manager: Callable[[], Any] | None = (
    # cache manager factory -- return type varies by implementation
    None  # TODO(rakesh): concreet retourtype vastleggen -- ADR-036 OP-53-nazorg
)

try:
    from src.core.caching.cache_layer import get_cache_manager

    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False

# Import types from central source
from src.core.types import AgentType

logger = logging.getLogger(__name__)


def _is_generated_agents_enabled() -> bool:
    """
    Check if generated agents should be loaded.

    Generated agents (src/core/agents/generated/) have empty capability catalogs
    and mislead the AgentRouter (B-016). Disabled by default in production.
    Set ENABLE_GENERATED_AGENTS=true for local development and testing only.
    """
    raw = os.getenv("ENABLE_GENERATED_AGENTS", "false")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class AgentStatus(Enum):
    """Agent status states"""

    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"
    SUSPENDED = "suspended"


@dataclass
class AgentDefinition:
    """Production agent definition with comprehensive metadata"""

    name: str
    module_path: str
    class_name: str
    agent_type: AgentType
    description: str
    capabilities: list[str]
    dependencies: list[str]
    resource_requirements: dict[
        str, object
    ]  # memory_mb: int, cpu_cores: int, disk_mb: int, network: bool
    performance_profile: dict[str, float]
    status: AgentStatus = AgentStatus.UNLOADED
    instance: Any = None  # active agent instance -- genuinely polymorphic
    load_error: str | None = None
    priority: int = 50  # 0-100, higher = more important
    version: str = "1.0.0"
    author: str = ""
    license: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_loaded: datetime | None = None


@dataclass
class LoaderConfiguration:
    """Loader configuration settings"""

    scan_directories: list[str]
    auto_discover: bool = True
    lazy_loading: bool = True
    dependency_resolution: bool = True
    performance_monitoring: bool = True
    cache_definitions: bool = True
    max_concurrent_loads: int = 5
    load_timeout: float = 30.0
    health_check_interval: int = 300  # seconds


class SubagentLoader:
    """Production-Ready Dynamic Subagent Loading and Management System"""

    def __init__(self, config: LoaderConfiguration | None = None) -> None:
        self.config = config or LoaderConfiguration(
            scan_directories=["core/agents", "core/subagents", "agents"]
        )

        self.agents: dict[str, AgentDefinition] = {}
        self.loaded_modules: dict[
            str, object
        ] = {}  # Python module objects -- types.ModuleType not imported to avoid circular
        self.agent_registry: dict[
            str, type["Agent"]
        ] = {}  # heterogeneous agent classes -- genuinely polymorphic
        self.active_agents: dict[
            str, "Agent"
        ] = {}  # heterogeneous agent instances -- genuinely polymorphic
        self.dependency_graph: dict[str, list[str]] = {}
        self.loading_locks: dict[str, asyncio.Lock] = {}
        self.cache_manager: Any = None
        self.health_monitor_task: asyncio.Task[None] | None = None
        self.running = False

        if CACHE_AVAILABLE and self.config.cache_definitions and get_cache_manager is not None:
            try:
                cache_mgr = get_cache_manager()
                if cache_mgr is not None:
                    self.cache_manager = cache_mgr
            except Exception as e:
                logger.warning(f"Cache manager unavailable: {e}")

        logger.info(
            f"SubagentLoader initialized with {len(self.config.scan_directories)} scan directories"
        )

    async def start_loader(self) -> None:
        """Start the loader with health monitoring"""
        if self.running:
            logger.warning("Loader already running")
            return

        self.running = True

        # Auto-discover agents if enabled
        if self.config.auto_discover:
            await self.discover_agents()

        # Start health monitoring
        if self.config.performance_monitoring:
            self.health_monitor_task = asyncio.create_task(self._health_monitor())

        logger.info("SubagentLoader started successfully")

    async def stop_loader(self) -> None:
        """Stop the loader and cleanup resources"""
        self.running = False

        if self.health_monitor_task:
            self.health_monitor_task.cancel()

        # Gracefully stop all active agents
        for agent_name in list(self.active_agents.keys()):
            await self._stop_agent(agent_name)

        logger.info("SubagentLoader stopped")

    async def discover_agents(self) -> list[AgentDefinition]:
        """Discover all available agents in configured directories"""
        discovered_agents: list[AgentDefinition] = []
        # Cache key includes flag state so flipping ENABLE_GENERATED_AGENTS
        # is reflected immediately without a stale cache hit (B-016 fix).
        flag_suffix = "enabled" if _is_generated_agents_enabled() else "disabled"
        cache_key = f"agent_definitions:{flag_suffix}"
        # Check cache first
        if self.cache_manager:
            cached_definitions = await self.cache_manager.get(cache_key)
            if cached_definitions:
                logger.info("Loading agent definitions from cache")
                for agent_data in cached_definitions:
                    agent_def = self._deserialize_agent_definition(agent_data)
                    if agent_def:
                        self.agents[agent_def.name] = agent_def
                        discovered_agents.append(agent_def)
                return discovered_agents

        # Scan directories for agents
        for scan_dir in self.config.scan_directories:
            scan_path = Path(scan_dir)
            if not scan_path.exists():
                logger.debug(f"Scan directory not found: {scan_path}")
                continue

            logger.info(f"Scanning directory: {scan_path}")

            for py_file in scan_path.rglob("*.py"):
                if self._should_skip_file(py_file):
                    continue

                try:
                    agent_defs = await self._analyze_agent_file(py_file)
                    for agent_def in agent_defs:
                        discovered_agents.append(agent_def)
                        self.agents[agent_def.name] = agent_def
                        logger.info(
                            f"Discovered agent: {agent_def.name} ({agent_def.agent_type.value})"
                        )

                except Exception as e:
                    logger.error(f"Error analyzing agent file {py_file}: {e}")

        # Build dependency graph
        await self._build_dependency_graph()

        # Cache discoveries (use flag-specific key so ENABLE_GENERATED_AGENTS changes
        # take effect immediately on next cache miss, not after 1-hour TTL expiry).
        if self.cache_manager and discovered_agents:
            serialized = [self._serialize_agent_definition(agent) for agent in discovered_agents]
            await self.cache_manager.set(cache_key, serialized, ttl=3600)

        logger.info(f"Discovered {len(discovered_agents)} agents")
        return discovered_agents

    def _should_skip_file(self, file_path: Path) -> bool:
        """Determine if a file should be skipped during discovery"""
        # Skip files starting with underscore
        if file_path.name.startswith("_"):
            return True

        # Skip init files
        if file_path.name == "__init__.py":
            return True

        # Skip backup files
        if file_path.suffix in [".bak", ".backup", ".old"]:
            return True

        # NOTE: Generated agents have empty capability catalogs (B-016).
        # Skip them unless ENABLE_GENERATED_AGENTS=true (default: false).
        if "generated" in file_path.parts and not _is_generated_agents_enabled():
            return True

        return False

    async def _analyze_agent_file(self, file_path: Path) -> list[AgentDefinition]:
        """Analyze a Python file for agent class definitions"""
        try:
            # Convert file path to module path
            relative_path = file_path.relative_to(Path.cwd())
            module_path = str(relative_path).replace(os.sep, ".").replace(".py", "")

            # Import and analyze the module
            spec = importlib.util.spec_from_file_location(module_path, file_path)
            if not spec or not spec.loader:
                return []

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find agent classes
            agent_definitions: list[AgentDefinition] = []
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if self._is_agent_class(obj) and obj.__module__ == module_path:
                    agent_def = await self._create_agent_definition(name, module_path, obj)
                    if agent_def:
                        agent_definitions.append(agent_def)

            return agent_definitions

        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            return []

    def _is_agent_class(self, cls: type[object]) -> bool:
        """Check if a class is a valid agent class.

        Bewust `bool` en GEEN `TypeGuard[type[Agent]]` (ADR-036 OP-53, hersteld 2026-08-31).
        Deze check vergelijkt MRO-NAMEN tegen een lijst tekenreeksen en valt daarna terug op
        "heeft een van de methoden execute/initialize/get_capabilities". Naamgelijkenis
        garandeert geen subklasse, dus een TypeGuard zou hier een onwaarheid vastleggen en
        die narrowing ook aan de rest van de lusbody opdringen. Zie de toelichting op
        `_create_agent_definition()` voor het volledige argument.

        De narrowing had geen werk meer: de enige aanroeper geeft het resultaat door aan
        `_create_agent_definition()`, dat `type[object]` accepteert. Gemeten 2026-08-31 met
        de TypeGuard weg: `run_mypy_audit.py --fail-on-increase` geeft total 0 / baseline 0
        (exit 0) en pyright 0 errors.
        """
        # Get base class names
        base_classes = [base.__name__ for base in cls.__mro__]

        # Check for agent base classes or naming patterns
        agent_indicators = [
            "BaseAgent",
            "Agent",
            "SpecialistAgent",
            "SubAgent",
            "CVAAgent",
            "UltimateAgent",
            "PerfectAgent",
        ]

        # Check base classes
        if any(indicator in base_classes for indicator in agent_indicators):
            return True

        # Check class name patterns
        if any(indicator in cls.__name__ for indicator in agent_indicators):
            return True

        # Check for required agent methods
        required_methods = ["execute", "initialize", "get_capabilities"]
        has_required_methods = any(hasattr(cls, method) for method in required_methods)

        return has_required_methods

    async def _create_agent_definition(
        self,
        class_name: str,
        module_path: str,
        agent_class: type[object],
    ) -> AgentDefinition | None:
        """Create an AgentDefinition from a class.

        `agent_class` is bewust `type[object]` en niet `type[Agent]` (ADR-036 OP-53, 2026-08-05).

        Deze functie leest uitsluitend OPTIONELE klasse-attributen met een default
        (`getattr(agent_class, "AGENT_NAME", class_name)` en tien soortgelijke) plus
        `inspect.getdoc`. Ze roept nergens iets aan dat het `Agent`-protocol vereist, dus de eis
        `type[Agent]` was een belofte die de functie niet nodig heeft.

        Waarom niet in plaats daarvan de AANROEPER laten narrowen: de enige aanroeper filtert met
        `_is_agent_class()`, en die vergelijkt MRO-NAMEN tegen een lijst tekenreeksen ("BaseAgent",
        "Agent", "SubAgent", ...). Naamgelijkenis garandeert geen subklasse, dus een
        `TypeGuard[type[Agent]]` zou daar een onwaarheid vastleggen -- een cast in vermomming. Het
        eerlijke type is het type dat de functie echt aankan.
        """
        try:
            # Extract metadata from class
            name = getattr(agent_class, "AGENT_NAME", class_name)
            agent_type_str = getattr(agent_class, "AGENT_TYPE", "generic")
            description = inspect.getdoc(agent_class) or "No description available"
            capabilities = getattr(agent_class, "CAPABILITIES", [])
            dependencies = getattr(agent_class, "DEPENDENCIES", [])
            priority = getattr(agent_class, "PRIORITY", 50)
            version = getattr(agent_class, "VERSION", "1.0.0")
            author = getattr(agent_class, "AUTHOR", "")
            license_info = getattr(agent_class, "LICENSE", "")

            # Parse agent type
            try:
                agent_type = AgentType(agent_type_str.lower())
            except ValueError:
                agent_type = AgentType.GENERIC

            # Extract resource requirements
            resource_requirements = getattr(
                agent_class,
                "RESOURCE_REQUIREMENTS",
                {"memory_mb": 100, "cpu_cores": 1, "disk_mb": 50, "network": False},
            )

            # Extract performance profile
            performance_profile = getattr(
                agent_class,
                "PERFORMANCE_PROFILE",
                {
                    "avg_execution_time": 1.0,
                    "throughput_per_minute": 60.0,
                    "reliability_score": 0.9,
                    "scalability_factor": 1.0,
                },
            )

            return AgentDefinition(
                name=name,
                module_path=module_path,
                class_name=class_name,
                agent_type=agent_type,
                description=description,
                capabilities=capabilities,
                dependencies=dependencies,
                resource_requirements=resource_requirements,
                performance_profile=performance_profile,
                priority=priority,
                version=version,
                author=author,
                license=license_info,
            )

        except Exception as e:
            logger.error(f"Error creating agent definition for {class_name}: {e}")
            return None

    async def load_agent(self, agent_name: str, force_reload: bool = False) -> bool:
        """Load a specific agent by name with dependency resolution"""
        if agent_name not in self.agents:
            logger.error(f"Agent {agent_name} not found in registry")
            return False

        # Check if already loaded
        agent_def = self.agents[agent_name]
        if agent_def.status == AgentStatus.LOADED and not force_reload:
            logger.info(f"Agent {agent_name} already loaded")
            return True

        # Prevent concurrent loading
        if agent_name not in self.loading_locks:
            self.loading_locks[agent_name] = asyncio.Lock()

        async with self.loading_locks[agent_name]:
            return await self._load_agent_internal(agent_name, force_reload)

    async def _load_agent_internal(self, agent_name: str, force_reload: bool) -> bool:
        """Internal agent loading implementation"""
        agent_def = self.agents.get(agent_name)
        if agent_def is None:
            logger.error(f"Agent {agent_name} not found in registry")
            return False
        try:
            agent_def.status = AgentStatus.LOADING
            agent_def.load_error = None

            logger.info(f"Loading agent: {agent_name}")

            # Load dependencies first
            if self.config.dependency_resolution:
                for dep_name in agent_def.dependencies:
                    if dep_name in self.agents:
                        if not await self.load_agent(dep_name):
                            raise Exception(f"Failed to load dependency: {dep_name}")

            # Check system dependencies
            if not await self._check_system_dependencies(agent_def):
                raise Exception("System dependencies not satisfied")

            # Import the module
            try:
                if force_reload and agent_def.module_path in sys.modules:
                    importlib.reload(sys.modules[agent_def.module_path])

                module = importlib.import_module(agent_def.module_path)
                self.loaded_modules[agent_def.module_path] = module
            except ImportError as e:
                raise Exception(f"Failed to import module {agent_def.module_path}: {e}")

            # Get the agent class
            try:
                agent_class = getattr(module, agent_def.class_name)
                self.agent_registry[agent_name] = agent_class
            except AttributeError as e:
                raise Exception(f"Agent class {agent_def.class_name} not found in module: {e}")

            # Validate agent class
            if not await self._validate_agent_class(agent_class):
                raise Exception("Agent class validation failed")

            agent_def.status = AgentStatus.LOADED
            agent_def.last_loaded = datetime.now(timezone.utc)

            logger.info(f"Successfully loaded agent: {agent_name}")
            return True

        except Exception as e:
            if agent_def is not None:
                agent_def.status = AgentStatus.ERROR
                agent_def.load_error = str(e)
            logger.error(f"Failed to load agent {agent_name}: {e}")
            return False

    async def _check_system_dependencies(self, agent_def: AgentDefinition) -> bool:
        """Check if system dependencies are satisfied"""
        try:
            # Check Python module dependencies
            for dep in agent_def.dependencies:
                if not dep.startswith("core."):  # External dependencies
                    try:
                        importlib.import_module(dep)
                    except ImportError:
                        logger.error(
                            f"External dependency {dep} not available for {agent_def.name}"
                        )
                        return False

            # Check resource requirements (basic validation)
            reqs = agent_def.resource_requirements
            memory_mb = reqs.get("memory_mb", 0)
            if isinstance(memory_mb, (int, float)) and memory_mb > 10000:  # > 10GB
                logger.warning(
                    f"Agent {agent_def.name} has high memory requirements: {memory_mb}MB"
                )

            return True

        except Exception as e:
            logger.error(f"System dependency check failed for {agent_def.name}: {e}")
            return False

    async def _validate_agent_class(self, agent_class: type["Agent"]) -> bool:
        """Validate that an agent class meets requirements"""
        try:
            # Check for required methods
            required_methods = ["execute"]
            for method in required_methods:
                if not hasattr(agent_class, method):
                    logger.error(f"Agent class missing required method: {method}")
                    return False

            # Check method signatures
            if hasattr(agent_class, "execute"):
                execute_method = getattr(agent_class, "execute")
                if not callable(execute_method):
                    logger.error("Execute method is not callable")
                    return False

            return True

        except Exception as e:
            logger.error(f"Agent class validation failed: {e}")
            return False

    async def instantiate_agent(
        self, agent_name: str, **kwargs: Any
    ) -> (
        # TODO(TYPE): replace Any with concrete type
        Any | None
    ):  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        """Instantiate a loaded agent with configuration"""
        try:
            # Ensure agent is loaded
            if agent_name not in self.agent_registry:
                if not await self.load_agent(agent_name):
                    return None

            # Check if already instantiated
            if agent_name in self.active_agents:
                logger.warning(f"Agent {agent_name} already instantiated")
                return self.active_agents[agent_name]

            agent_class = self.agent_registry[agent_name]
            agent_def = self.agents[agent_name]

            # Prepare initialization parameters
            init_params = {"agent_name": agent_name, "loader_instance": self, **kwargs}

            # Instantiate the agent
            agent_instance = agent_class(**init_params)

            # Initialize if the agent has an initialize method
            if hasattr(agent_instance, "initialize"):
                if asyncio.iscoroutinefunction(
                    agent_instance.initialize  # pyright: ignore[reportAttributeAccessIssue]
                ):
                    await agent_instance.initialize()  # pyright: ignore[reportAttributeAccessIssue]
                else:
                    agent_instance.initialize()  # pyright: ignore[reportAttributeAccessIssue]

            # Register as active
            self.active_agents[agent_name] = agent_instance
            agent_def.status = AgentStatus.ACTIVE
            agent_def.instance = agent_instance

            logger.info(f"Instantiated agent: {agent_name}")
            return agent_instance

        except Exception as e:
            logger.error(f"Failed to instantiate agent {agent_name}: {e}")
            if agent_name in self.agents:
                self.agents[agent_name].status = AgentStatus.ERROR
                self.agents[agent_name].load_error = str(e)
            return None

    async def reload_agent(self, agent_name: str) -> bool:
        """Reload an agent (useful for development)"""
        try:
            # Stop active instance if exists
            if agent_name in self.active_agents:
                await self._stop_agent(agent_name)

            # Remove from registry
            if agent_name in self.agent_registry:
                del self.agent_registry[agent_name]

            # Reset agent definition
            if agent_name in self.agents:
                agent_def = self.agents[agent_name]
                if agent_def.module_path in self.loaded_modules:
                    del self.loaded_modules[agent_def.module_path]

                # Reload module if in sys.modules
                if agent_def.module_path in sys.modules:
                    importlib.reload(sys.modules[agent_def.module_path])

                agent_def.status = AgentStatus.UNLOADED
                agent_def.instance = None
                agent_def.load_error = None

            # Reload the agent
            return await self.load_agent(agent_name, force_reload=True)

        except Exception as e:
            logger.error(f"Error reloading agent {agent_name}: {e}")
            return False

    async def _stop_agent(self, agent_name: str) -> None:
        """Stop and cleanup an active agent"""
        try:
            if agent_name in self.active_agents:
                agent = self.active_agents[agent_name]

                # Call stop method if available
                if hasattr(agent, "stop"):
                    if asyncio.iscoroutinefunction(
                        agent.stop  # pyright: ignore[reportAttributeAccessIssue]
                    ):
                        await agent.stop()  # pyright: ignore[reportAttributeAccessIssue]
                    else:
                        agent.stop()  # pyright: ignore[reportAttributeAccessIssue]

                del self.active_agents[agent_name]

            if agent_name in self.agents:
                self.agents[agent_name].status = AgentStatus.LOADED
                self.agents[agent_name].instance = None

            logger.info(f"Stopped agent: {agent_name}")

        except Exception as e:
            logger.error(f"Error stopping agent {agent_name}: {e}")

    async def load_all_agents(self) -> dict[str, bool]:
        """Load all discovered agents with respect to priorities"""
        results: dict[str, bool] = {}
        # Sort by priority (higher priority first)
        sorted_agents = sorted(self.agents.values(), key=lambda x: x.priority, reverse=True)

        # Load agents in batches to respect max_concurrent_loads
        semaphore = asyncio.Semaphore(self.config.max_concurrent_loads)

        async def load_single_agent(agent_def: AgentDefinition) -> bool:
            async with semaphore:
                success = await self.load_agent(agent_def.name)
                results[agent_def.name] = success
                return success

        # Create tasks for all agents
        tasks = [load_single_agent(agent_def) for agent_def in sorted_agents]

        # Wait for all to complete
        await asyncio.gather(*tasks, return_exceptions=True)

        return results

    async def _build_dependency_graph(self) -> None:
        """Build dependency graph for agents"""
        self.dependency_graph = {}

        for agent_name, agent_def in self.agents.items():
            self.dependency_graph[agent_name] = []

            for dep in agent_def.dependencies:
                if dep.startswith("core.agents.") or dep in self.agents:
                    # Extract agent name from dependency
                    dep_agent_name = dep.split(".")[-1] if "." in dep else dep
                    if dep_agent_name in self.agents:
                        self.dependency_graph[agent_name].append(dep_agent_name)

    async def _health_monitor(self) -> None:
        """Monitor health of active agents"""
        while self.running:
            try:
                datetime.now(timezone.utc)

                for agent_name, agent_instance in list(self.active_agents.items()):
                    try:
                        # Check if agent has health check method
                        if hasattr(agent_instance, "health_check"):
                            # getattr in plaats van attribuut-toegang plus een ignore:
                            # de hasattr-guard hierboven IS al de voorwaarde, dus een
                            # onderdrukking voegt hier niets toe.
                            health_check = getattr(agent_instance, "health_check")
                            if asyncio.iscoroutinefunction(health_check):
                                health_status = await health_check()
                            else:
                                health_status = health_check()

                            if not health_status:
                                logger.warning(f"Agent {agent_name} failed health check")

                    except Exception as e:
                        logger.error(f"Health check failed for {agent_name}: {e}")

                await asyncio.sleep(self.config.health_check_interval)

            except Exception as e:
                logger.error(f"Error in health monitor: {e}")
                await asyncio.sleep(60)

    def get_agent(self, agent_name: str) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Get an active agent instance"""
        return self.active_agents.get(agent_name)

    def get_agents_by_type(self, agent_type: AgentType | str) -> list["Agent"]:
        """Get all active agents of a specific type"""
        if isinstance(agent_type, str):
            try:
                agent_type = AgentType(agent_type.lower())
            except ValueError:
                return []

        return [
            agent
            for name, agent in self.active_agents.items()
            if self.agents[name].agent_type == agent_type
        ]

    def get_agent_status(self, agent_name: str) -> AgentStatus | None:
        """Get the status of an agent"""
        agent_def = self.agents.get(agent_name)
        return agent_def.status if agent_def else None

    def list_available_agents(
        self,
    ) -> list[dict[str, object]]:
        """List all available agents with their status"""
        return [
            {
                "name": agent_def.name,
                "type": agent_def.agent_type.value,
                "status": agent_def.status.value,
                "description": agent_def.description,
                "capabilities": agent_def.capabilities,
                "priority": agent_def.priority,
                "version": agent_def.version,
                "error": agent_def.load_error,
                "last_loaded": agent_def.last_loaded.isoformat() if agent_def.last_loaded else None,
            }
            for agent_def in self.agents.values()
        ]

    def get_metrics(self) -> dict[str, object]:
        """Get comprehensive loader metrics"""
        status_counts: dict[str, int] = {}
        for status in AgentStatus:
            status_counts[status.value] = sum(
                1 for agent in self.agents.values() if agent.status == status
            )

        type_counts: dict[str, int] = {}
        for agent_type in AgentType:
            type_counts[agent_type.value] = sum(
                1 for agent in self.agents.values() if agent.agent_type == agent_type
            )

        return {
            "total_agents": len(self.agents),
            "loaded_agents": len(self.agent_registry),
            "active_agents": len(self.active_agents),
            "status_distribution": status_counts,
            "type_distribution": type_counts,
            "loaded_modules": len(self.loaded_modules),
            "dependency_graph_size": len(self.dependency_graph),
            "scan_directories": self.config.scan_directories,
            "loader_running": self.running,
        }

    def _serialize_agent_definition(self, agent_def: AgentDefinition) -> dict[str, object]:
        """Serialize agent definition for caching"""
        return {
            "name": agent_def.name,
            "module_path": agent_def.module_path,
            "class_name": agent_def.class_name,
            "agent_type": agent_def.agent_type.value,
            "description": agent_def.description,
            "capabilities": agent_def.capabilities,
            "dependencies": agent_def.dependencies,
            "resource_requirements": agent_def.resource_requirements,
            "performance_profile": agent_def.performance_profile,
            "priority": agent_def.priority,
            "version": agent_def.version,
            "author": agent_def.author,
            "license": agent_def.license,
            "created_at": agent_def.created_at.isoformat(),
        }

    def _deserialize_agent_definition(self, data: dict[str, object]) -> AgentDefinition | None:
        """Deserialize agent definition from cache"""
        try:
            return AgentDefinition(
                name=cast(str, data["name"]),
                module_path=cast(str, data["module_path"]),
                class_name=cast(str, data["class_name"]),
                agent_type=AgentType(cast(str, data["agent_type"])),
                description=cast(str, data["description"]),
                capabilities=cast(list[str], data["capabilities"]),
                dependencies=cast(list[str], data["dependencies"]),
                resource_requirements=cast(dict[str, object], data["resource_requirements"]),
                performance_profile=cast(dict[str, float], data["performance_profile"]),
                priority=cast(int, data["priority"]),
                version=cast(str, data["version"]),
                author=cast(str, data["author"]),
                license=cast(str, data["license"]),
                created_at=datetime.fromisoformat(cast(str, data["created_at"])),
            )
        except Exception as e:
            logger.error(f"Failed to deserialize agent definition: {e}")
            return None

    def get_subagents_by_category(self, category: str) -> list[AgentDefinition]:
        """Get subagents by category/type name"""
        matching_agents: list[AgentDefinition] = []
        category_lower = category.lower()

        for agent_def in self.agents.values():
            # Check agent type name
            if hasattr(agent_def.agent_type, "value"):
                type_name = str(agent_def.agent_type.value).lower()
            else:
                type_name = str(agent_def.agent_type).lower()

            if category_lower in type_name or type_name in category_lower:
                matching_agents.append(agent_def)
                continue

            # Check capabilities
            for cap in agent_def.capabilities:
                if category_lower in cap.lower():
                    matching_agents.append(agent_def)
                    break

        return matching_agents

    def get_all_subagents(self) -> list[AgentDefinition]:
        """Get all subagent definitions"""
        return list(self.agents.values())


# Global loader instance (thread-safe singleton)
import threading as _threading

_global_loader: SubagentLoader | None = None
_loader_lock = _threading.Lock()


def get_loader() -> SubagentLoader:
    """Get the global subagent loader instance (thread-safe singleton)."""
    global _global_loader
    if _global_loader is None:
        with _loader_lock:
            if _global_loader is None:  # double-checked locking
                _global_loader = SubagentLoader()
    return _global_loader


def initialize_loader(
    config: LoaderConfiguration | None = None,
    force: bool = False,
) -> SubagentLoader:
    """Initialize the global subagent loader.

    If a loader already exists and force=False, the existing loader is
    returned unchanged. Pass force=True only during application startup
    before any component has called get_loader().
    """
    global _global_loader
    if _global_loader is not None and not force:
        logger.debug("initialize_loader: singleton already exists, returning existing instance")
        return _global_loader
    with _loader_lock:
        # Double-checked: another thread may have initialized between the outer check and the lock
        if _global_loader is None or force:
            _global_loader = SubagentLoader(config)
    return _global_loader


def reset_loader() -> None:
    """Reset the global loader instance (test utility only)."""
    global _global_loader
    with _loader_lock:
        _global_loader = None


# Production configuration factory
def create_production_config() -> LoaderConfiguration:
    """Create production loader configuration"""
    return LoaderConfiguration(
        scan_directories=["core/agents", "agents"],
        auto_discover=True,
        lazy_loading=True,
        dependency_resolution=True,
        performance_monitoring=True,
        cache_definitions=True,
        max_concurrent_loads=3,
        load_timeout=60.0,
        health_check_interval=600,
    )


# Exports for main.py compatibility
def get_subagent_loader() -> SubagentLoader:
    """Get the global subagent loader instance"""
    return get_loader()
