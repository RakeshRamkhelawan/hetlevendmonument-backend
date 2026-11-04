"""Schema's voor handmatige invoer van debiteuren (debiteurenagent dag 2).

`extra="forbid"` op de invoer: een veld dat er niet hoort -- `tenant_id` voorop -- geeft een 422
in plaats van stil te worden genegeerd. De tenant komt uitsluitend uit de JWT (CLAUDE.md, NOOIT-lijst).
`source` en `external_id` staan er bewust niet in: handmatige invoer is altijd `handmatig`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from pydantic.networks import validate_email
from pydantic_core import PydanticCustomError

_VALUTA = r"^[A-Z]{3}$"
#: Geen regeleinden of stuurtekens: naam en factuurnummer komen in het onderwerp en de tekst
#: van een brief, en een latere e-mailverzender mag geen header-injectie erven (security-review dag 2).
_EEN_REGEL = r"^[^\x00-\x1f\x7f]+$"


#: Deel van de Engelse reden van de bibliotheek bij een gereserveerd domein (zoals `.test`); alleen om de goede
#: Nederlandse tekst te kiezen, de Engelse tekst zelf gaat nooit naar de klant.
_GERESERVEERD = "special-use or reserved"


def _controleer_email(waarde: str) -> str:
    """Dezelfde controle en dezelfde genormaliseerde uitkomst als `EmailStr`, met een eigen Nederlandse melding.

    Zonder dit gaf een adres op `.test` een 422 met de Engelse tekst van de bibliotheek; het scherm kon niet zeggen welk veld
    en waarom (acceptatie 2026-10-22). De soort `ongeldig_email` laat het scherm de tekst overnemen.
    """
    try:
        return validate_email(waarde)[1]
    except PydanticCustomError as exc:
        if _GERESERVEERD in exc.message():
            tekst = (
                "Het e-mailadres is niet geldig: het deel na de apenstaart is een gereserveerde naam "
                "(zoals .test) die niet voor e-mail bestaat."
            )
        else:
            tekst = "Het e-mailadres is niet geldig. Gebruik een adres zoals naam@bedrijf.nl."
        raise PydanticCustomError("ongeldig_email", tekst) from exc


# `format: email` blijft in het OpenAPI-schema staan (dat deed `EmailStr` zelf); `json_schema_extra` laat de lengtegrens
# van het veld ongemoeid, `WithJsonSchema` zou het hele schema vervangen.
KlantEmail = Annotated[
    str,
    AfterValidator(_controleer_email),
    Field(json_schema_extra={"format": "email"}),
]


class ReceivableCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(pattern=_EEN_REGEL, min_length=1, max_length=200)
    customer_email: KlantEmail = Field(max_length=320)
    invoice_number: str = Field(pattern=_EEN_REGEL, min_length=1, max_length=100)
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="EUR", pattern=_VALUTA)
    due_date: date


class ReceivableUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name: str | None = Field(default=None, pattern=_EEN_REGEL, min_length=1, max_length=200)
    customer_email: KlantEmail | None = Field(default=None, max_length=320)
    invoice_number: str | None = Field(default=None, pattern=_EEN_REGEL, min_length=1, max_length=100)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, pattern=_VALUTA)
    due_date: date | None = None
    # `geescaleerd` zet de opvolgactor en `herinnerd` de verzendlus, op het moment dat de brief
    # aantoonbaar is verstuurd. Een gebruiker (of een workflow met een token) zet geen van beide.
    status: Literal["open", "betaald"] | None = None
    # Verplicht bij terug van `betaald`; de repository toetst dat.
    reden: str | None = Field(default=None, pattern=_EEN_REGEL, min_length=1, max_length=500)


class ReceivableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_name: str
    customer_email: str
    invoice_number: str
    amount: Decimal
    currency: str
    due_date: date
    status: str
    source: str
    created_at: datetime
    herinnerd_op: datetime | None = None
    betaald_op: datetime | None = None


class ReminderProposalRequest(BaseModel):
    """De knop "Herinnering voorstellen": welke facturen, en welke soort brief (dag 3).

    Hoogstens 20 per keer: elke factuur is een eigen agentactie met een eigen Council-beoordeling.
    """

    model_config = ConfigDict(extra="forbid")

    receivable_ids: list[int] = Field(min_length=1, max_length=20)
    kind: Literal["herinnering", "aanmaning"] = "herinnering"
