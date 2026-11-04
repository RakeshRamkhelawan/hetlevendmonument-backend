"""Het API-contract voor `amount` blijft punt-decimaal (plan-van-aanpak-nazorg deel II punt 3).

De frontend zet "1250,00" om naar "1250.00" (`frontend/src/lib/bedrag.ts`). De API zelf blijft
locale-vrij: andere klanten (importen, koppelingen) mogen niet afhangen van een gok over "1.250".
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from src.core.api.v1.receivables.schemas import ReceivableCreate

_BASIS: dict[str, Any] = {
    "customer_name": "Bakkerij De Korst",
    "customer_email": "administratie@dekorst.example",
    "invoice_number": "F-1",
    "currency": "EUR",
    "due_date": "2026-09-01",
}


@pytest.mark.parametrize("bedrag", ["1250,00", "1.250,00", "-5", "12.345"])
def test_een_bedrag_buiten_het_contract_wordt_geweigerd(bedrag: str) -> None:
    with pytest.raises(ValidationError):
        ReceivableCreate.model_validate({**_BASIS, "amount": bedrag})


def test_een_bedrag_met_punt_wordt_geaccepteerd() -> None:
    """Andere kant op: het contract zelf werkt."""
    model = ReceivableCreate.model_validate({**_BASIS, "amount": "1250.00"})

    assert str(model.amount) == "1250.00"
