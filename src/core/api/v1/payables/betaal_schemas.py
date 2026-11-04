"""Schema van de aanvraag om het betaalbestand (crediteuren dag 3).

`extra="forbid"`: een veld dat er niet hoort, `tenant_id` voorop, geeft een 422. Het IBAN en de naam zijn die van het EIGEN bedrijf (de
rekening waar het geld vanaf gaat); ze worden in het bestand gezet en nergens bewaard.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


#: Een reden van minstens tien tekens (zonder omringende spaties): "ok" is geen reden. Zelfde ondergrens als het afwijzen van een ticket.
REDEN_MIN = 10


class IntrekkenAanvraag(BaseModel):
    """Een goedgekeurde factuur intrekken (crediteuren nazorg). De reden is verplicht en komt in het auditlog."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reden: str = Field(min_length=REDEN_MIN, max_length=500)


class VoorstelIntrekkenAanvraag(IntrekkenAanvraag):
    """Een goedgekeurd betaalvoorstel intrekken, zolang het betaalbestand nog niet is gemaakt."""

    ticket_ref: str = Field(min_length=1, max_length=50)


class BetaalbestandAanvraag(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    #: Op naam van wie de rekening staat; komt als opdrachtgever in het bestand (hoogstens 70 tekens in SEPA).
    debiteur_naam: str = Field(min_length=1, max_length=70)
    #: Het eigen IBAN van de rekening waarvan wordt betaald. Spaties zijn toegestaan; de server controleert de controlesom.
    debiteur_iban: str = Field(min_length=15, max_length=42)
    #: De dag waarop de bank moet uitvoeren; niet in het verleden.
    uitvoerdatum: date
