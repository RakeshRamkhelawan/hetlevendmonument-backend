"""SMTP-dubbel op de systeemgrens, gedeeld door de verzendtests van Keten B dag 2.

Vervangen wordt ALLEEN `aiosmtplib.send`, de laatste functie voor het netwerk. De mailservice
(`SMTPEmailService`), `get_email_service()` en de actor lopen echt. Zo toetsen de tests wat er
werkelijk de deur uit gaat, en niet dat een interne functie werd aangeroepen.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from email.message import Message

import aiosmtplib
import pytest


@dataclass
class OntvangenBrief:
    """Een brief zoals de SMTP-kant hem ziet."""

    bericht: Message
    opties: dict[str, object]

    @property
    def afzender(self) -> str:
        return str(self.bericht["From"])

    @property
    def ontvanger(self) -> str:
        return str(self.bericht["To"])

    @property
    def onderwerp(self) -> str:
        return str(self.bericht["Subject"])

    @property
    def tekst(self) -> str:
        """Het platte-tekstdeel van de brief."""
        delen = self.bericht.get_payload()
        assert isinstance(delen, list) and delen, "verwacht een brief met onderdelen"
        inhoud = delen[0].get_payload(decode=True)
        assert isinstance(inhoud, bytes)
        return inhoud.decode("utf-8")

    @property
    def alle_delen(self) -> str:
        """Alle onderdelen van de brief (tekst en html) achter elkaar."""
        delen = self.bericht.get_payload()
        assert isinstance(delen, list)
        return "\n".join(
            (d.get_payload(decode=True) or b"").decode("utf-8")  # type: ignore[union-attr]
            for d in delen
        )


@dataclass
class SmtpDubbel:
    """Neemt de plaats in van `aiosmtplib.send`."""

    ontvangen: list[OntvangenBrief] = field(default_factory=list)
    #: Aan deze ontvangers weigert de "server" de brief (verbinding verbroken).
    weiger_voor: set[str] = field(default_factory=set)
    #: Weiger alles.
    weiger_alles: bool = False
    #: Tekst van de fout; mag een geheim bevatten, om te meten dat het niet doorlekt.
    foutboodschap: str = "connection refused"
    #: Wachttijd per verzending, om gelijktijdige runs te laten overlappen.
    vertraging: float = 0.0
    #: Per verzending: de tenantcontext zoals de aanroeper die op dat moment had.
    tenantcontext_per_verzending: list[int | None] = field(default_factory=list)
    #: Aantal pogingen, ook de geweigerde.
    pogingen: int = 0

    async def send(self, bericht: Message, **opties: object) -> tuple[dict[str, object], str]:
        from src.core.middleware.tenant_context import get_current_tenant_id

        self.pogingen += 1
        self.tenantcontext_per_verzending.append(get_current_tenant_id())
        if self.vertraging:
            await asyncio.sleep(self.vertraging)
        if self.weiger_alles or str(bericht["To"]) in self.weiger_voor:
            raise aiosmtplib.SMTPConnectError(self.foutboodschap)
        self.ontvangen.append(OntvangenBrief(bericht=bericht, opties=dict(opties)))
        return {}, "250 OK"


def installeer_smtp_dubbel(monkeypatch: pytest.MonkeyPatch) -> SmtpDubbel:
    dubbel = SmtpDubbel()
    monkeypatch.setattr(aiosmtplib, "send", dubbel.send)
    return dubbel


def zet_testmailbox(monkeypatch: pytest.MonkeyPatch, *, wachtwoord: str | None = None) -> None:
    """Zet de omgeving zoals lokaal met Mailpit: SMTP_HOST gezet, afzender los van de inlognaam."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SMTP_HOST", "mailpit")
    monkeypatch.setenv("SMTP_PORT", "1025")
    monkeypatch.setenv("EMAIL_FROM", "noreply@sanskritisetu.org")
    monkeypatch.delenv("SMTP_USER", raising=False)
    if wachtwoord is None:
        monkeypatch.delenv("SMTP_USERNAME", raising=False)
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("SMTP_USERNAME", "inlog@smtp.example")
        monkeypatch.setenv("SMTP_PASSWORD", wachtwoord)
