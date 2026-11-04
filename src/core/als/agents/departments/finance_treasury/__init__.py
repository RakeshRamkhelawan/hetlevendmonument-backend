"""Finance & Treasury Department Agents.

5 Agents:
    - AccountsReceivablePayableAgent (ML): Invoice processing, payment management
    - TaxComplianceAgent (LLM): Tax analysis, compliance reporting
    - InvestmentAllocationAgent (ML): Portfolio optimization, capital allocation
    - ForecastingAgent (ML): Financial forecasting, budgeting
    - AuditComplianceAgent (ML): Internal audit, compliance checking
"""

from typing import Any

from src.core.als.agents.departments.finance_treasury.accounts_receivable_payable_agent import (
    AccountsReceivablePayableAgent,
)
from src.core.als.agents.departments.finance_treasury.audit_compliance_agent import (
    AuditComplianceAgent,
)
from src.core.als.agents.departments.finance_treasury.forecasting_agent import ForecastingAgent
from src.core.als.agents.departments.finance_treasury.investment_allocation_agent import (
    InvestmentAllocationAgent,
)
from src.core.als.agents.departments.finance_treasury.tax_compliance_agent import TaxComplianceAgent

__all__ = [
    "AccountsReceivablePayableAgent",
    "TaxComplianceAgent",
    "InvestmentAllocationAgent",
    "ForecastingAgent",
    "AuditComplianceAgent",
]
