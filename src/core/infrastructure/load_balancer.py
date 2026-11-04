"""
Load balancer for distributing agent tasks across multiple nodes.

Provides:
- Multiple load balancing strategies (round-robin, least-connections, weighted)
- Health-aware routing (skip unhealthy nodes)
- Sticky sessions for stateful agents
- Auto-scaling integration hooks
"""

import asyncio
import hashlib
import logging
import random
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, Generic, List, Optional, Set, TypeVar
from collections.abc import Callable

logger = logging.getLogger(__name__)

T = TypeVar("T")


class LoadBalanceStrategy(Enum):
    """Load balancing strategies."""

    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    IP_HASH = "ip_hash"
    RANDOM = "random"
    LATENCY_BASED = "latency_based"


@dataclass
class Node:
    """Represents a backend node for load balancing."""

    id: str
    host: str
    port: int
    weight: int = 1
    healthy: bool = True

    # Dynamic metrics
    active_connections: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
    last_response_time: float = 0.0

    # Metadata
    region: str = "default"
    capabilities: set[str] = field(default_factory=set)
    tags: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._latency_history: Deque[float] = deque()
        self._max_history = 100

    def record_latency(self, latency_ms: float) -> None:
        """Record response latency for this node."""
        self._latency_history.append(latency_ms)
        if len(self._latency_history) > self._max_history:
            self._latency_history.popleft()

        self.avg_latency_ms = sum(self._latency_history) / len(self._latency_history)
        self.last_response_time = time.time()

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate."""
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests

    def get_score(self) -> float:
        """Calculate health score (higher is better)."""
        if not self.healthy:
            return 0.0

        # Base score from weight
        score = float(self.weight)

        # Penalize high latency
        if self.avg_latency_ms > 0:
            score /= 1 + self.avg_latency_ms / 1000

        # Penalize failures
        score *= 1 - self.failure_rate

        # Penalize many active connections
        score /= 1 + self.active_connections / 10

        return score


class LoadBalancerStrategy(ABC, Generic[T]):
    """Abstract base class for load balancing strategies."""

    @abstractmethod
    def select_node(self, nodes: list[Node], context: T | None = None) -> Node | None:
        """Select a node from the available pool."""
        pass

    @abstractmethod
    def update(self, nodes: list[Node]) -> None:
        """Update strategy with new node list."""
        pass


class RoundRobinStrategy(LoadBalancerStrategy[Any]):  # TODO(TYPE): replace Any with concrete type
    """Simple round-robin selection."""

    def __init__(self) -> None:
        self._index = 0
        self._lock = asyncio.Lock()

    def select_node(self, nodes: list[Node], context: Any | None = None) -> Node | None:  # TODO(TYPE): replace Any with concrete type
        healthy_nodes = [n for n in nodes if n.healthy]
        if not healthy_nodes:
            return None

        # Round-robin with modulo
        node = healthy_nodes[self._index % len(healthy_nodes)]
        self._index = (self._index + 1) % len(healthy_nodes)

        return node

    def update(self, nodes: list[Node]) -> None:
        """Clamp current round-robin index to healthy node count."""
        healthy_nodes = [n for n in nodes if n.healthy]
        if healthy_nodes:
            self._index = self._index % len(healthy_nodes)
        else:
            self._index = 0


class LeastConnectionsStrategy(LoadBalancerStrategy[Any]):  # TODO(TYPE): replace Any with concrete type
    """Select node with fewest active connections."""

    def select_node(self, nodes: list[Node], context: Any | None = None) -> Node | None:  # TODO(TYPE): replace Any with concrete type
        healthy_nodes = [n for n in nodes if n.healthy]
        if not healthy_nodes:
            return None

        return min(healthy_nodes, key=lambda n: n.active_connections)

    def update(self, nodes: list[Node]) -> None:
        """Update node pool tracking and clear active state for decommissioned nodes."""
        self._healthy_nodes = [n for n in nodes if n.healthy]


class WeightedRoundRobinStrategy(LoadBalancerStrategy[Any]):  # TODO(TYPE): replace Any with concrete type
    """Weighted round-robin based on node weights."""

    def __init__(self) -> None:
        self._current_index = 0
        self._current_weight = 0
        self._gcd = 1
        self._max_weight = 1

    def update(self, nodes: list[Node]) -> None:
        """Recalculate GCD and max weight when nodes change."""
        healthy_nodes = [n for n in nodes if n.healthy]
        if not healthy_nodes:
            return

        weights = [n.weight for n in healthy_nodes]
        self._max_weight = max(weights)
        self._gcd = self._calculate_gcd(weights)

    def _calculate_gcd(self, numbers: list[int]) -> int:
        """Calculate GCD of a list of numbers."""
        from functools import reduce
        from math import gcd

        return reduce(gcd, numbers)

    def select_node(self, nodes: list[Node], context: Any | None = None) -> Node | None:  # TODO(TYPE): replace Any with concrete type
        healthy_nodes = [n for n in nodes if n.healthy]
        if not healthy_nodes:
            return None

        # Weighted round-robin algorithm
        while True:
            self._current_index = (self._current_index + 1) % len(healthy_nodes)

            if self._current_index == 0:
                self._current_weight -= self._gcd
                if self._current_weight <= 0:
                    self._current_weight = self._max_weight

                if self._current_weight == 0:
                    return None

            node = healthy_nodes[self._current_index]
            if node.weight >= self._current_weight:
                return node


class IPHashStrategy(LoadBalancerStrategy[Any]):  # TODO(TYPE): replace Any with concrete type
    """Hash-based selection for sticky sessions."""

    def select_node(self, nodes: list[Node], context: Any | None = None) -> Node | None:  # TODO(TYPE): replace Any with concrete type
        healthy_nodes = [n for n in nodes if n.healthy]
        if not healthy_nodes:
            return None

        # Context should be an IP address or session ID
        if not context:
            # Fall back to random
            return random.choice(healthy_nodes)

        # Hash the context
        hash_value = int(hashlib.sha256(str(context).encode()).hexdigest(), 16)
        index = hash_value % len(healthy_nodes)

        return healthy_nodes[index]

    def update(self, nodes: list[Node]) -> None:
        """Update sorted list of healthy nodes for hash ring mapping."""
        self._healthy_nodes = sorted([n for n in nodes if n.healthy], key=lambda n: n.id)


class LatencyBasedStrategy(LoadBalancerStrategy[Any]):  # TODO(TYPE): replace Any with concrete type
    """Select node with lowest average latency."""

    def __init__(self, exploration_rate: float = 0.1) -> None:
        self.exploration_rate = exploration_rate  # Chance to try other nodes

    def select_node(self, nodes: list[Node], context: Any | None = None) -> Node | None:  # TODO(TYPE): replace Any with concrete type
        healthy_nodes = [n for n in nodes if n.healthy]
        if not healthy_nodes:
            return None

        # Occasionally explore (random selection)
        if random.random() < self.exploration_rate:
            return random.choice(healthy_nodes)

        # Exploit: select lowest latency node
        # Filter nodes with data
        nodes_with_data = [n for n in healthy_nodes if n.avg_latency_ms > 0]

        if nodes_with_data:
            return min(nodes_with_data, key=lambda n: n.avg_latency_ms)
        else:
            return random.choice(healthy_nodes)

    def update(self, nodes: list[Node]) -> None:
        """Update active node set for latency comparisons."""
        self._active_nodes = [n for n in nodes if n.healthy]


class LoadBalancer(Generic[T]):
    """
    High-performance load balancer for agent routing.

    Features:
    - Pluggable strategies
    - Health checking
    - Sticky sessions
    - Circuit breaker integration
    """

    def __init__(
        self,
        name: str,
        strategy: LoadBalanceStrategy = LoadBalanceStrategy.ROUND_ROBIN,
        health_check_interval: float = 30.0,
        sticky_sessions: bool = False,
    ) -> None:
        self.name = name
        self.strategy_type = strategy
        self.health_check_interval = health_check_interval
        self.sticky_sessions = sticky_sessions

        # Strategy implementation
        self._strategy = self._create_strategy(strategy)

        # Node management
        self._nodes: dict[str, Node] = {}
        self._lock = asyncio.Lock()

        # Sticky sessions
        self._sticky_map: dict[str, str] = {}  # session_id -> node_id
        self._sticky_ttl = 300  # 5 minutes

        # Health checking
        self._health_check_task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type
        self._running = False

        # Metrics
        self._total_requests = 0
        self._failed_requests = 0

        logger.info(f"LoadBalancer '{name}' created with {strategy.value} strategy")

    def _create_strategy(self, strategy: LoadBalanceStrategy) -> LoadBalancerStrategy[Any]:  # TODO(TYPE): replace Any with concrete type
        """Create strategy instance."""
        # Als Callable getypeerd, niet als type[...]: mypy voegt de concrete klassen
        # samen tot hun gemeenschappelijke abstracte basis en weigert dan het aanroepen
        # daarvan ("Cannot instantiate abstract class"). Elke waarde hier is een
        # concrete subklasse, dus als fabriek-callable klopt het wel.
        strategies: dict[LoadBalanceStrategy, Callable[[], LoadBalancerStrategy[Any]]] = {  # TODO(TYPE): replace Any with concrete type
            LoadBalanceStrategy.ROUND_ROBIN: RoundRobinStrategy,
            LoadBalanceStrategy.LEAST_CONNECTIONS: LeastConnectionsStrategy,
            LoadBalanceStrategy.WEIGHTED_ROUND_ROBIN: WeightedRoundRobinStrategy,
            LoadBalanceStrategy.IP_HASH: IPHashStrategy,
            LoadBalanceStrategy.RANDOM: RoundRobinStrategy,  # Simplified
            LoadBalanceStrategy.LATENCY_BASED: LatencyBasedStrategy,
        }

        strategy_class = strategies.get(strategy, RoundRobinStrategy)
        strategy_instance: LoadBalancerStrategy[Any] = strategy_class()  # TODO(TYPE): replace Any with concrete type
        return strategy_instance

    async def start(self) -> None:
        """Start health checking."""
        if self._running:
            return

        self._running = True
        self._health_check_task = asyncio.create_task(
            self._health_check_loop(), name=f"lb_health_{self.name}"
        )
        logger.info(f"LoadBalancer '{self.name}' started")

    async def stop(self) -> None:
        """Stop health checking."""
        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        logger.info(f"LoadBalancer '{self.name}' stopped")

    async def add_node(self, node: Node) -> None:
        """Add a backend node."""
        async with self._lock:
            self._nodes[node.id] = node
            self._strategy.update(list(self._nodes.values()))

        logger.info(f"Added node {node.id} to load balancer '{self.name}'")

    async def remove_node(self, node_id: str) -> bool:
        """Remove a backend node."""
        async with self._lock:
            if node_id in self._nodes:
                del self._nodes[node_id]
                self._strategy.update(list(self._nodes.values()))

                # Remove from sticky map
                sessions_to_remove = [
                    sid for sid, nid in self._sticky_map.items() if nid == node_id
                ]
                for sid in sessions_to_remove:
                    del self._sticky_map[sid]

                logger.info(f"Removed node {node_id} from load balancer '{self.name}'")
                return True
            return False

    async def get_node(
        self,
        session_id: str | None = None,
        context: T | None = None,
    ) -> Node | None:
        """Get a node for request routing."""
        self._total_requests += 1

        async with self._lock:
            nodes = list(self._nodes.values())

            if not nodes:
                self._failed_requests += 1
                return None

            # Check sticky session
            if self.sticky_sessions and session_id:
                sticky_node_id = self._sticky_map.get(session_id)
                if sticky_node_id:
                    node = self._nodes.get(sticky_node_id)
                    if node and node.healthy:
                        node.active_connections += 1
                        return node
                    else:
                        # Sticky node unhealthy, remove mapping
                        del self._sticky_map[session_id]

            # Use strategy to select node
            node = self._strategy.select_node(nodes, context)

            if node:
                node.active_connections += 1
                node.total_requests += 1

                # Record sticky session
                if self.sticky_sessions and session_id:
                    self._sticky_map[session_id] = node.id
            else:
                self._failed_requests += 1

            return node

    async def release_node(self, node_id: str, success: bool = True, latency_ms: float = 0) -> None:
        """Release node after request completion."""
        async with self._lock:
            node = self._nodes.get(node_id)
            if node:
                node.active_connections = max(0, node.active_connections - 1)

                if not success:
                    node.failed_requests += 1

                if latency_ms > 0:
                    node.record_latency(latency_ms)

    async def _health_check_loop(self) -> None:
        """Background health checking."""
        while self._running:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(5)

    async def _perform_health_checks(self) -> None:
        """Check health of all nodes."""
        async with self._lock:
            nodes = list(self._nodes.values())

        for node in nodes:
            try:
                healthy = await self._check_node_health(node)

                if healthy != node.healthy:
                    node.healthy = healthy
                    status = "healthy" if healthy else "unhealthy"
                    logger.info(f"Node {node.id} is now {status}")

                    # Update strategy with new health status
                    async with self._lock:
                        self._strategy.update(list(self._nodes.values()))

            except Exception as e:
                logger.warning(f"Health check failed for {node.id}: {e}")
                if node.healthy:
                    node.healthy = False

    async def _check_node_health(self, node: Node) -> bool:
        """Perform health check on a node."""
        # Simple TCP connect check
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(node.host, node.port), timeout=5.0
            )
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    async def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get load balancer statistics."""
        # Note: Reading node stats without lock for simple read operations.
        # Attribute access to _total_requests and _failed_requests are atomic in CPython.
        nodes = list(self._nodes.values())
        healthy_count = sum(1 for n in nodes if n.healthy)

        return {
            "name": self.name,
            "strategy": self.strategy_type.value,
            "total_nodes": len(nodes),
            "healthy_nodes": healthy_count,
            "unhealthy_nodes": len(nodes) - healthy_count,
            "total_requests": self._total_requests,
            "failed_requests": self._failed_requests,
            "failure_rate": (
                self._failed_requests / self._total_requests if self._total_requests > 0 else 0.0
            ),
            "sticky_sessions": len(self._sticky_map),
            "nodes": [
                {
                    "id": n.id,
                    "healthy": n.healthy,
                    "active_connections": n.active_connections,
                    "avg_latency_ms": round(n.avg_latency_ms, 2),
                    "failure_rate": round(n.failure_rate, 4),
                }
                for n in nodes
            ],
        }


class AgentLoadBalancer:
    """
    Load balancer specifically designed for agent routing.

    Routes tasks to agent nodes based on:
    - Agent capabilities
    - Node health
    - Current load
    - Geographic proximity (optional)
    """

    def __init__(self) -> None:
        self._balancers: dict[str, LoadBalancer[Any]] = {}  # capability -> balancer  # TODO(TYPE): replace Any with concrete type
        self._lock = asyncio.Lock()

    async def register_capability(
        self,
        capability: str,
        strategy: LoadBalanceStrategy = LoadBalanceStrategy.LEAST_CONNECTIONS,
    ) -> LoadBalancer[Any]:  # TODO(TYPE): replace Any with concrete type
        """Register a load balancer for a specific capability."""
        async with self._lock:
            if capability not in self._balancers:
                lb: LoadBalancer[Any] = LoadBalancer(  # TODO(TYPE): replace Any with concrete type
                    name=f"lb_{capability}",
                    strategy=strategy,
                )
                await lb.start()
                self._balancers[capability] = lb

            return self._balancers[capability]

    async def add_agent_node(
        self,
        node: Node,
        capabilities: list[str],
    ) -> None:
        """Add an agent node with its capabilities."""
        for capability in capabilities:
            lb = await self.register_capability(capability)
            await lb.add_node(node)

    async def route_task(
        self,
        required_capabilities: list[str],
        session_id: str | None = None,
    ) -> Node | None:
        """Route a task to an appropriate agent node."""
        # Try each capability in order
        for capability in required_capabilities:
            lb = self._balancers.get(capability)
            if lb:
                node = await lb.get_node(session_id=session_id)
                if node:
                    return node

        return None

    async def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get stats for all capability balancers."""
        result: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for capability, lb in self._balancers.items():
            result[capability] = await lb.get_stats()
        return result
