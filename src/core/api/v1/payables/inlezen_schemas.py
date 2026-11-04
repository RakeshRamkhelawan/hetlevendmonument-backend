"""Schema van de bevestiging bij het inlezen van een inkoopfactuur (crediteuren dag 2).

`extra="forbid"`: een veld dat er niet hoort, `tenant_id` voorop, geeft een 422. De velden zijn die van `PayableCreate` (dezelfde
regels voor factuurnummer, bedrag in hele centen en valuta), maar de leverancier is OF een bestaande (`supplier_id`) OF een nieuwe
(`nieuwe_leverancier`): precies een van de twee.
"""

from __future__ import annotations

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schemas import _EEN_REGEL, _VALUTA, Bedrag, SupplierCreate


class InlezenBevestiging(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    supplier_id: int | None = Field(default=None, gt=0)
    nieuwe_leverancier: SupplierCreate | None = None
    #: Het IBAN op de factuur, zoals de medewerker het bevestigt; alleen voor een bestaande leverancier (bij een nieuwe
    #: leverancier staat het IBAN in `nieuwe_leverancier`). Wijkt het af van dat van de leverancier, dan eist de server
    #: `iban_afwijking_bevestigd`.
    iban: str | None = Field(default=None, max_length=64)
    iban_afwijking_bevestigd: bool = False
    #: AANPASSEN: de factuur hoort bij een ticket van de crediteurenagent. Wie aanpast heeft het goedkeurrecht, geeft een reden
    #: (die in het ticket komt) en het ticket sluit als "afgewezen, handmatig vastgelegd" met een verwijzing naar de factuur.
    ticket_ref: str = Field(pattern=r"^hitl_[0-9a-f]{8,40}$")
    reden: str = Field(min_length=10, max_length=1000)
    invoice_number: str = Field(pattern=_EEN_REGEL, min_length=1, max_length=100)
    amount_cents: Bedrag
    currency: str = Field(default="EUR", pattern=_VALUTA)
    invoice_date: date
    due_date: date

    @model_validator(mode="after")
    def _een_leverancier(self) -> Self:
        if (self.supplier_id is None) == (self.nieuwe_leverancier is None):
            raise ValueError("kies een bestaande leverancier of vul een nieuwe leverancier in, niet beide en niet geen")
        return self
