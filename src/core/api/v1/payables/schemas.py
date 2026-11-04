"""Schema's voor leveranciers en inkoopfacturen (crediteuren dag 1).

`extra="forbid"` op de invoer: een veld dat er niet hoort -- `tenant_id` voorop -- geeft een 422 in plaats van stil te worden
genegeerd. De tenant komt uitsluitend uit de JWT (CLAUDE.md, NOOIT-lijst).

**Geld is een geheel aantal centen.** `amount_cents` is `StrictInt`: een komma-getal, een tekst of een `true` geeft een 422, ook
als het naar een getal om te zetten is. Of het bedrag groter is dan nul toetst de repository, met een Nederlandse tekst.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from src.core.api.v1.receivables.schemas import KlantEmail

_VALUTA = r"^[A-Z]{3}$"
#: Geen stuurtekens, onzichtbare tekens (nulbreed, bidi-omkering) of regel- en alineascheiders (Unicode Cc, Cf, Zl, Zp; Gate 2): naam en factuurnummer komen straks in een betaalbestand en in een brief, en een latere
#: verzender mag geen header-injectie erven (zelfde reden als bij debiteuren).
_EEN_REGEL = r"^[^\p{Cc}\p{Cf}\p{Zl}\p{Zp}]+$"
#: Boven dit bedrag is het vrijwel zeker een typefout (een miljard euro); de database kan veel meer (BIGINT).
MAX_BEDRAG_CENTEN = 100_000_000_000

Bedrag = Annotated[StrictInt, Field(le=MAX_BEDRAG_CENTEN)]


class SupplierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(pattern=_EEN_REGEL, min_length=1, max_length=200)
    #: Ruwe invoer met spaties; de repository normaliseert en controleert het nummer (modulo 97).
    iban: str | None = Field(default=None, max_length=64)
    email: KlantEmail | None = Field(default=None, max_length=320)


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    iban: str | None = None
    email: str | None = None
    created_at: datetime


class PayableCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    supplier_id: int = Field(gt=0)
    invoice_number: str = Field(pattern=_EEN_REGEL, min_length=1, max_length=100)
    amount_cents: Bedrag
    currency: str = Field(default="EUR", pattern=_VALUTA)
    invoice_date: date
    due_date: date


class PayableUpdate(BaseModel):
    """Dag 1 kent een enkele wijziging: de status. De repository zegt welke stappen er al zijn."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: str = Field(min_length=1, max_length=20)


class PayableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    supplier_name: str
    invoice_number: str
    amount_cents: int
    currency: str
    invoice_date: date
    due_date: date
    status: str
    created_at: datetime
    checked_at: datetime | None = None
