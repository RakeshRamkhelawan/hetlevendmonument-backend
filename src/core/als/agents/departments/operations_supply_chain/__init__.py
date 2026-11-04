"""Operations & Supply Chain Department Agents.

4 Agents:
    - ProcessMiningAgent (ML): Process analysis, optimization
    - InventoryForecasterAgent (ML): Demand forecasting, inventory optimization
    - VendorNegotiationAgent (LLM): Supplier negotiation, contract terms
    - LogisticsOptimizationAgent (ML): Route optimization, fleet management
"""

from typing import Any

from src.core.als.agents.departments.operations_supply_chain.inventory_forecaster import (
    InventoryForecasterAgent,
)
from src.core.als.agents.departments.operations_supply_chain.logistics_optimization_agent import (
    LogisticsOptimizationAgent,
)
from src.core.als.agents.departments.operations_supply_chain.process_mining_agent import (
    ProcessMiningAgent,
)
from src.core.als.agents.departments.operations_supply_chain.vendor_negotiation_agent import (
    VendorNegotiationAgent,
)

__all__ = [
    "ProcessMiningAgent",
    "InventoryForecasterAgent",
    "VendorNegotiationAgent",
    "LogisticsOptimizationAgent",
]
