"""Het sjabloon voor een betalingsherinnering en een aanmaning (debiteurenagent dag 2).

**Waarom een sjabloon in code en geen taalmodel (besluit 3 van dag 1).** De goedkeurder moet
precies de brief zien die verstuurd wordt. Een model dat de tekst schrijft, schrijft bij
uitvoeren een andere tekst dan bij aanvragen; een sjabloon geeft twee keer hetzelfde. Daarom
rendert de agent de brief VOOR het ticket, en rendert de tool hem bij uitvoeren opnieuw en
vergelijkt (`receivables_registry._send_payment_reminder`).

**Deterministisch, dus geen datum van vandaag in de tekst.** Tussen aanvragen en goedkeuren kan
een nacht zitten; een zin als "nu 12 dagen te laat" zou de goedgekeurde tekst dan ongeldig maken.

De tekst is een eerste versie in gewone taal en is niet juridisch getoetst (open vraag voor
Rakesh, zie de brief van dag 2). ASCII-only, zoals alle code in dit project.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

#: De twee soorten brief. `aanmaning` is de tweede, strengere stap na een herinnering.
REMINDER_KINDS = ("herinnering", "aanmaning")


@dataclass(frozen=True)
class RenderedReminder:
    """Wat er verstuurd wordt: aan wie, met welk onderwerp, met welke tekst."""

    recipient: str
    subject: str
    body: str


def _bedrag(amount: Decimal, currency: str) -> str:
    return f"{currency} {amount.quantize(Decimal('0.01'))}"


def render_payment_reminder(
    *,
    kind: str,
    customer_name: str,
    customer_email: str,
    invoice_number: str,
    amount: Decimal,
    currency: str,
    due_date: date,
) -> RenderedReminder:
    """Render de brief. Gooit `ValueError` bij een onbekende soort."""
    if kind not in REMINDER_KINDS:
        raise ValueError(f"onbekende soort brief: {kind!r}")

    bedrag = _bedrag(amount, currency)
    vervaldatum = due_date.isoformat()
    if kind == "herinnering":
        onderwerp = f"Herinnering: factuur {invoice_number}"
        kern = (
            f"Volgens onze administratie staat factuur {invoice_number} van {bedrag} nog open. "
            f"De vervaldatum was {vervaldatum}. Wilt u het bedrag zo spoedig mogelijk "
            "overmaken? Heeft u al betaald, dan kunt u deze herinnering als niet verzonden "
            "beschouwen."
        )
    else:
        onderwerp = f"Aanmaning: factuur {invoice_number}"
        kern = (
            f"Ondanks onze eerdere herinnering staat factuur {invoice_number} van {bedrag} nog "
            f"open. De vervaldatum was {vervaldatum}. Wij verzoeken u het bedrag binnen 14 dagen "
            "na dagtekening van deze brief over te maken. Neem bij vragen of een geschil "
            "contact met ons op."
        )
    tekst = f"Beste {customer_name},\n\n{kern}\n\nMet vriendelijke groet,\nDe debiteurenadministratie"
    return RenderedReminder(recipient=customer_email, subject=onderwerp, body=tekst)
