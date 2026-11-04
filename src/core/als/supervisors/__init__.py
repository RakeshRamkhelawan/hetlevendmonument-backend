"""Supervisor hierarchy for SanskritiSetu multi-agent system."""

from typing import Any

from src.core.als.supervisors.base_supervisor import BaseSupervisor
from src.core.als.supervisors.finance_supervisor import FinanceSupervisor

__all__ = ["BaseSupervisor", "FinanceSupervisor"]
