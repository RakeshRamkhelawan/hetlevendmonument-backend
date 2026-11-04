"""
Golden Demo Templates - Fase 1

Drie no-cost, productieharde demo workflows:
- D1: Intake -> Offerte -> Review (Sales)
- D2: Order -> Fulfilment simulatie (Operations)
- D3: Factuurcontrole -> Approval (Finance)
"""

from typing import Any

from src.core.demos.templates.d1_intake_offerte import D1Configuration, D1Template
from src.core.demos.templates.d2_order_fulfilment import D2Configuration, D2Template
from src.core.demos.templates.d3_factuur_controle import D3Configuration, D3Template

__all__ = [
    "D1Template",
    "D1Configuration",
    "D2Template",
    "D2Configuration",
    "D3Template",
    "D3Configuration",
]
