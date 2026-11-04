"""TDD unit tests for LoadBalancer and routing strategies.

Tests coverage:
- RoundRobinStrategy with dynamic node pool updates
- LeastConnectionsStrategy with active connection tracking
- WeightedRoundRobinStrategy with GCD weight recalculation
- IPHashStrategy with sticky context hashing
- LatencyBasedStrategy with latency tracking
- LoadBalancer core with health checking and strategy delegation
"""

import pytest

from src.core.infrastructure.load_balancer import (
    IPHashStrategy,
    LatencyBasedStrategy,
    LeastConnectionsStrategy,
    LoadBalancer,
    LoadBalanceStrategy,
    Node,
    RoundRobinStrategy,
    WeightedRoundRobinStrategy,
)


def test_round_robin_strategy_genuine():
    nodes = [
        Node(id="n1", host="10.0.0.1", port=8001, healthy=True),
        Node(id="n2", host="10.0.0.2", port=8002, healthy=True),
        Node(id="n3", host="10.0.0.3", port=8003, healthy=False),
    ]
    strategy = RoundRobinStrategy()
    strategy.update(nodes)

    selected = [strategy.select_node(nodes).id for _ in range(4)]
    assert selected == ["n1", "n2", "n1", "n2"]

    # When node 2 becomes unhealthy and strategy updates:
    nodes[1].healthy = False
    strategy.update(nodes)
    selected_after = [strategy.select_node(nodes).id for _ in range(2)]
    assert selected_after == ["n1", "n1"]


def test_least_connections_strategy_genuine():
    nodes = [
        Node(id="n1", host="10.0.0.1", port=8001, active_connections=5, healthy=True),
        Node(id="n2", host="10.0.0.2", port=8002, active_connections=1, healthy=True),
        Node(id="n3", host="10.0.0.3", port=8003, active_connections=0, healthy=False),
    ]
    strategy = LeastConnectionsStrategy()
    strategy.update(nodes)

    selected = strategy.select_node(nodes)
    assert selected is not None
    assert selected.id == "n2"


def test_weighted_round_robin_strategy_genuine():
    nodes = [
        Node(id="n1", host="10.0.0.1", port=8001, weight=3, healthy=True),
        Node(id="n2", host="10.0.0.2", port=8002, weight=1, healthy=True),
    ]
    strategy = WeightedRoundRobinStrategy()
    strategy.update(nodes)

    selected = [strategy.select_node(nodes).id for _ in range(4)]
    assert selected.count("n1") == 3
    assert selected.count("n2") == 1


def test_ip_hash_strategy_genuine():
    nodes = [
        Node(id="n1", host="10.0.0.1", port=8001, healthy=True),
        Node(id="n2", host="10.0.0.2", port=8002, healthy=True),
    ]
    strategy = IPHashStrategy()
    strategy.update(nodes)

    # Consistent routing for the same IP
    node_a1 = strategy.select_node(nodes, context="192.168.1.100")
    node_a2 = strategy.select_node(nodes, context="192.168.1.100")
    assert node_a1 is not None
    assert node_a1.id == node_a2.id

    # Fallback when no context
    random_node = strategy.select_node(nodes, context=None)
    assert random_node is not None


def test_latency_based_strategy_genuine():
    n1 = Node(id="n1", host="10.0.0.1", port=8001, healthy=True)
    n1.record_latency(150.0)
    n2 = Node(id="n2", host="10.0.0.2", port=8002, healthy=True)
    n2.record_latency(20.0)

    strategy = LatencyBasedStrategy(exploration_rate=0.0)
    strategy.update([n1, n2])

    selected = strategy.select_node([n1, n2])
    assert selected is not None
    assert selected.id == "n2"


@pytest.mark.asyncio
async def test_load_balancer_e2e_routing():
    lb = LoadBalancer[str](name="test_lb", strategy=LoadBalanceStrategy.ROUND_ROBIN)
    n1 = Node(id="n1", host="10.0.0.1", port=8001, healthy=True)
    n2 = Node(id="n2", host="10.0.0.2", port=8002, healthy=True)

    await lb.add_node(n1)
    await lb.add_node(n2)

    node1 = await lb.get_node()
    node2 = await lb.get_node()
    assert {node1.id, node2.id} == {"n1", "n2"}
