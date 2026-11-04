"""
Premium Connectors voor Nederlandse Markt

Deze connectoren hebben externe kosten en zijn beschikbaar als premium add-ons.
Zie README.md voor volledig kostenoverzicht.
"""

from enum import Enum
from typing import Any, Dict, Optional


class PremiumConnector(Enum):
    """Premium connectors met externe kosten"""

    MOLLIE = "mollie"
    KVK = "kvk"
    BELASTINGDIENST = "belastingdienst"
    IBAN_CHECK = "iban_check"
    EXACT_ONLINE = "exact_online"
    AFAS = "afas"
    POSTNL = "postnl"
    TEAMLEADER = "teamleader"


class CostModel:
    """Kostenmodel voor een premium connector"""

    def __init__(
        self,
        fixed_monthly: float = 0.0,
        per_call: float = 0.0,
        per_transaction: float = 0.0,
        requires_license: bool = False,
        notes: str = "",
    ) -> None:
        self.fixed_monthly = fixed_monthly
        self.per_call = per_call
        self.per_transaction = per_transaction
        self.requires_license = requires_license
        self.notes = notes

    def estimate_monthly_cost(self, calls: int = 0, transactions: int = 0) -> float:
        """Schat maandkosten op basis van gebruik"""
        return self.fixed_monthly + (calls * self.per_call) + (transactions * self.per_transaction)


# Kostenmodellen per connector
PREMIUM_COSTS = {
    PremiumConnector.MOLLIE: CostModel(
        per_transaction=0.29,
        notes="iDEAL EUR0.29, CC 1.8%+EUR0.25",  # iDEAL gemiddeld
    ),
    PremiumConnector.KVK: CostModel(
        fixed_monthly=6.40, per_call=0.02, notes="EUR6.40/maand + EUR0.02 per bevraging"
    ),
    PremiumConnector.BELASTINGDIENST: CostModel(
        fixed_monthly=19.50, notes="Via Bokkz.nl middleware"
    ),
    PremiumConnector.IBAN_CHECK: CostModel(
        per_call=0.10,
        requires_license=True,
        notes="Currence partnerschap vereist",  # Geschat
    ),
    PremiumConnector.EXACT_ONLINE: CostModel(
        requires_license=True, notes="Exact Online licentie vereist (vanaf EUR30/maand)"
    ),
    PremiumConnector.AFAS: CostModel(requires_license=True, notes="AFAS licentie vereist"),
    PremiumConnector.POSTNL: CostModel(
        per_transaction=6.00,
        notes="EUR4.50-EUR7.50 per zending",  # Gemiddeld pakket
    ),
    PremiumConnector.TEAMLEADER: CostModel(
        requires_license=True, notes="Teamleader Focus abonnement vereist"
    ),
}


def get_cost_estimate(
    connectors: list[PremiumConnector],
    calls_per_month: dict[str, int] | None = None,
    transactions_per_month: dict[str, int] | None = None,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Bereken totale maandkosten voor geselecteerde premium connectoren.

    Voorbeeld:
        get_cost_estimate(
            [PremiumConnector.KVK, PremiumConnector.MOLLIE],
            calls_per_month={"kvk": 500},
            transactions_per_month={"mollie": 100}
        )
    """
    calls = calls_per_month or {}
    transactions = transactions_per_month or {}

    total = 0.0
    breakdown: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    for conn in connectors:
        cost_model = PREMIUM_COSTS[conn]
        conn_calls = calls.get(conn.value, 0)
        conn_transactions = transactions.get(conn.value, 0)

        cost = cost_model.estimate_monthly_cost(conn_calls, conn_transactions)
        total += cost

        breakdown[conn.value] = {
            "fixed_monthly": cost_model.fixed_monthly,
            "call_costs": conn_calls * cost_model.per_call,
            "transaction_costs": conn_transactions * cost_model.per_transaction,
            "requires_license": cost_model.requires_license,
            "notes": cost_model.notes,
            "total": cost,
        }

    return {"total_monthly": total, "breakdown": breakdown}


# Quick reference voor klanten
PREMIUM_PACK_PRICE = 49.0  # EUR/maand

PREMIUM_PACK_INCLUDES = [
    PremiumConnector.MOLLIE,
    PremiumConnector.KVK,  # Tot 500 calls
    PremiumConnector.POSTNL,
    PremiumConnector.TEAMLEADER,
]


def is_included_in_premium_pack(connector: PremiumConnector) -> bool:
    """Check of connector inbegrepen is in Premium Pack"""
    return connector in PREMIUM_PACK_INCLUDES
