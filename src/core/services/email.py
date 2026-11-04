"""
Email Service Interface

Abstract email sending service with multiple backend support.

Part of SC-5.2 implementation.
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from src.core.services.email_templates import STANDAARD_SJABLONENMAP

logger = logging.getLogger(__name__)

# Template directory (can be overridden via env). Standaard dezelfde map als de sjabloonengine
# (`email_templates.STANDAARD_SJABLONENMAP`): een tweede, andere standaardmap was de reden dat de sjablonen
# nooit werden gevonden.
TEMPLATE_DIR = Path(os.getenv("EMAIL_TEMPLATE_DIR") or STANDAARD_SJABLONENMAP)

#: Afzender als er geen `EMAIL_FROM` en geen inlognaam is (Mailpit heeft geen inlog en weigert een lege
#: `From`). Het eigen domein van het product, nooit een adres van een klant.
STANDAARD_AFZENDER = "noreply@sanskritisetu.org"


@dataclass
class EmailMessage:
    """Email message data class."""

    to: str | list[str]
    subject: str
    body: str
    html_body: str | None = None
    cc: list[str] | None = None
    bcc: list[str] | None = None
    reply_to: str | None = None


class EmailServiceInterface(ABC):
    """Abstract base class for email services."""

    @abstractmethod
    async def send(self, message: EmailMessage) -> bool:
        """
        Send an email.

        Args:
            message: EmailMessage object containing email details

        Returns:
            True if sent successfully, False otherwise
        """
        pass

    @abstractmethod
    async def send_template(
        self, to: str | list[str], template_name: str, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """
        Send an email using a template.

        Args:
            to: Recipient email address(es)
            template_name: Name of the email template
            context: Template context variables

        Returns:
            True if sent successfully, False otherwise
        """
        pass

    def _render_template(self, template_name: str, context: dict[str, Any]) -> tuple[str, str]:  # TODO(TYPE): replace Any with concrete type
        """
        Render a Jinja2 template.

        Args:
            template_name: Name of template file (without extension)
            context: Template variables

        Returns: Tuple[Any, ...] of (subject, body_html)  # TODO(TYPE): replace Any with concrete type
        """
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape

            env = Environment(
                loader=FileSystemLoader(TEMPLATE_DIR),
                autoescape=select_autoescape(["html", "xml"]),
            )

            # Load template
            template = env.get_template(f"{template_name}.html")
            html_body = template.render(**context)

            # Extract subject from context or use template name
            subject = context.get("subject", template_name.replace("_", " ").title())

            return subject, html_body

        except ImportError:
            logger.warning("Jinja2 not installed, using fallback template rendering")
            subject = context.get("subject", template_name)
            body = "Template: %s\n\n" % template_name + "\n".join(
                "%s: %s" % (k, v) for k, v in context.items()
            )
            return subject, body
        except Exception as exc:
            logger.error("template_rendering_failed: %s", exc)
            raise


class ConsoleEmailService(EmailServiceInterface):
    """Console email service for development/testing."""

    async def send(self, message: EmailMessage) -> bool:
        """Log email to console instead of sending."""
        logger.info("email_dispatch_success: service=console")
        return True

    async def send_template(
        self, to: str | list[str], template_name: str, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """Log template email to console."""
        subject, body = self._render_template(template_name, context)
        logger.info("template_email_dispatch: template=%s", template_name)
        logger.debug("template_body_preview: %s", body[:500])
        return True


def _niet_leeg(waarde: str | None) -> str | None:
    """De waarde zonder omringende spaties, of None als er niets overblijft."""
    return (waarde or "").strip() or None


class SMTPEmailService(EmailServiceInterface):
    """SMTP email service for production."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
    ) -> None:
        ingesteld_host, ingestelde_poort = _smtp_instellingen()
        self.host = host or ingesteld_host or "localhost"
        self.port = port or ingestelde_poort or 587
        # Een gezette maar lege variabele (`SMTP_USER=` in .env.local) is "niet ingesteld": een lege tekst
        # in plaats van None laat aiosmtplib inloggen, en een server zonder authenticatie verbreekt dan.
        self.username = (
            _niet_leeg(username) or _niet_leeg(os.getenv("SMTP_USERNAME")) or _niet_leeg(os.getenv("SMTP_USER"))
        )
        self.password = (_niet_leeg(password) or _niet_leeg(os.getenv("SMTP_PASSWORD"))) if self.username else None
        self.from_email = os.getenv("EMAIL_FROM") or self.username or STANDAARD_AFZENDER
        self.use_tls = use_tls

    async def send(self, message: EmailMessage) -> bool:
        """Send email via SMTP."""
        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            try:
                import aiosmtplib
            except ImportError:  # pragma: no cover - optional dependency
                logger.error("aiosmtplib not installed")
                return False

            msg = MIMEMultipart("alternative")
            msg["Subject"] = message.subject
            msg["From"] = self.from_email or self.username or ""
            msg["To"] = message.to if isinstance(message.to, str) else ", ".join(message.to)

            msg.attach(MIMEText(message.body, "plain"))
            if message.html_body:
                msg.attach(MIMEText(message.html_body, "html"))

            # Port 587 uses STARTTLS, port 465 uses implicit TLS
            use_tls = self.use_tls and self.port == 465
            start_tls = self.port == 587

            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                use_tls=use_tls,
                start_tls=start_tls,
            )
            logger.info("email_dispatch_success: service=smtp")
            return True
        except Exception as exc:
            logger.error(
                "email_dispatch_failed: %s: %s",
                type(exc).__name__, exc, exc_info=True
            )
            return False

    async def send_template(
        self, to: str | list[str], template_name: str, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """Send template email via SMTP."""
        try:
            subject, html_body = self._render_template(template_name, context)
            return await self.send(
                EmailMessage(
                    to=to,
                    subject=subject,
                    body=html_body,  # Fallback plain text
                    html_body=html_body,
                )
            )
        except Exception as exc:
            logger.error(
                "template_email_failed: %s: %s",
                type(exc).__name__, exc, exc_info=True
            )
            return False


class NietGeconfigureerdeEmailService(EmailServiceInterface):
    """Geen mailinstelling buiten tests: elke poging is een zichtbare fout, nooit een stille `True`.

    Gemeten 2026-10-15: de console-variant gaf bij een lokaal draaiend hostproces zonder `SMTP_HOST`
    `True` terug zonder iets te versturen; een beheerder zag "Actief", de mailbox bleef leeg en
    niemand wist waarom. Nu staat er een ERROR in het log en krijgt de aanroeper `False`.
    """

    _OORZAAK = (
        "er is geen mailinstelling (SMTP_HOST ontbreekt in de omgeving en in de app-configuratie); "
        "de e-mail is NIET verstuurd"
    )

    async def send(self, message: EmailMessage) -> bool:
        logger.error("email_not_configured: %s", self._OORZAAK)
        return False

    async def send_template(
        self, to: str | list[str], template_name: str, context: dict[str, object]
    ) -> bool:
        logger.error("email_not_configured: %s (template=%s)", self._OORZAAK, template_name)
        return False


def _smtp_uit_configuratie() -> tuple[str | None, int | None]:
    """`SMTP_HOST` en `SMTP_PORT` uit de app-configuratie, die `.env` WEL leest.

    `.env` komt niet vanzelf in `os.environ`; de rest van de configuratie leest hem via
    `UnifiedConfig`, en nu de mailinstelling ook. `importlib` zodat deze dienst geen nieuwe statische
    koppeling naar `config` krijgt (fan-out-budget, zelfde keuze als `receivables/dependencies.py`).
    Een configuratie die niet te lezen is geeft "niet ingesteld": dan volgt de zichtbare fout.
    """
    import importlib

    try:
        module = importlib.import_module("src.core.config.unified_config")
        config = module.UnifiedConfig.get_instance()
        host = (config.smtp_host or "").strip() or None
        poort = int(config.smtp_port) if host else None
    except Exception as exc:
        logger.warning(
            "smtp_config_unreadable: %s: %s", type(exc).__name__, exc, exc_info=True
        )
        return None, None
    return host, poort


def _smtp_instellingen() -> tuple[str | None, int | None]:
    """(host, poort): eerst `os.environ`, daarna de app-configuratie (niet in tests).

    Een lege `SMTP_HOST` (compose zet hem leeg als hij niet gevuld is) telt als "niet gezet". In tests
    (`TESTING=1`) leest dit de configuratie NIET: de uitkomst hangt daar alleen van de omgeving af en
    niet van de `.env` op de machine van wie de test draait.
    """
    host = os.getenv("SMTP_HOST", "").strip() or None
    poort: int | None = None
    poort_tekst = os.getenv("SMTP_PORT", "").strip()
    if poort_tekst:
        try:
            poort = int(poort_tekst)
        except ValueError:
            logger.error("smtp_port_invalid: SMTP_PORT is geen getal; de poort wordt genegeerd")
    if host is None and os.getenv("TESTING") != "1":
        host, config_poort = _smtp_uit_configuratie()
        if poort is None:
            poort = config_poort
    return host, poort


def get_email_service() -> EmailServiceInterface:
    """De mailservice voor deze omgeving.

    - SMTP: `SMTP_HOST` is ingesteld (omgeving of app-configuratie), of production/staging.
    - Console: ALLEEN in tests (`TESTING=1`); die variant verstuurt niets.
    - Anders: een dienst die elke poging als fout meldt (log ERROR en `False`).
    """
    env = os.getenv("ENVIRONMENT", "development").lower()
    host, _poort = _smtp_instellingen()

    if env in ("production", "staging") or host:
        logger.info("using_email_service: type=smtp")
        return SMTPEmailService()
    if os.getenv("TESTING") == "1":
        logger.info("using_email_service: type=console")
        return ConsoleEmailService()
    logger.error("using_email_service: type=niet_geconfigureerd (geen SMTP_HOST)")
    return NietGeconfigureerdeEmailService()


async def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    """
    Send password reset email using configured email service.

    Uses the existing EmailTemplateEngine with password_reset.html template.
    PII (to_email, reset_url) is NEVER logged.

    Geeft terug of de mail is verstuurd; de aanroeper laat dat niet vallen (een mislukte mail moet
    zichtbaar zijn, niet stil).
    """
    service = get_email_service()

    from src.core.services.email_templates import email_templates

    rendered = email_templates.render(
        "password_reset.html",
        subject="Wachtwoord opnieuw instellen -- SanskritiSetu",
        context={
            "user_name": to_email.split("@")[0],
            "reset_url": reset_url,
            "expiry_hours": 1,
        },
    )

    msg = EmailMessage(
        to=to_email,
        subject=rendered.subject,
        body=rendered.text_body
        or f"Gebruik deze link om een nieuw wachtwoord te kiezen: {reset_url}",
        html_body=rendered.html_body,
    )

    return await service.send(msg)


#: Hoe lang de link in een uitnodiging werkt. Langer dan een wachtwoordherstel (een uur): een nieuwe
#: medewerker opent de mail niet altijd meteen. Zelfde Redis-sleutel en dezelfde route als herstel.
UITNODIGING_GELDIG_UREN = 48


def bouw_uitnodiging(to_email: str, link: str) -> EmailMessage:
    """De uitnodigingsmail voor een nieuwe medewerker, in gewone Nederlandse taal.

    Er staat geen wachtwoord in: de medewerker kiest dat zelf via de eenmalige link. De tekst is
    zelf opgebouwd en niet via de sjabloonengine, waarvan de terugvaloptie de hele context (met de
    link) in de mail zou zetten.
    """
    import html

    onderwerp = "Uw uitnodiging voor SanskritiSetu"
    tekst = (
        "Goedendag,\n\n"
        "U bent uitgenodigd voor SanskritiSetu. Kies zelf uw wachtwoord via deze link:\n\n"
        f"{link}\n\n"
        f"De link werkt {UITNODIGING_GELDIG_UREN} uur en maar een keer. Na het kiezen van uw "
        "wachtwoord kunt u inloggen.\n\n"
        "Heeft u deze uitnodiging niet verwacht? Dan kunt u deze e-mail negeren.\n\n"
        "Met vriendelijke groet,\nSanskritiSetu\n"
    )
    veilig = html.escape(link, quote=True)
    html_tekst = (
        "<p>Goedendag,</p>"
        "<p>U bent uitgenodigd voor SanskritiSetu. Kies zelf uw wachtwoord via deze link:</p>"
        f'<p><a href="{veilig}">{veilig}</a></p>'
        f"<p>De link werkt {UITNODIGING_GELDIG_UREN} uur en maar een keer. Na het kiezen van uw "
        "wachtwoord kunt u inloggen.</p>"
        "<p>Heeft u deze uitnodiging niet verwacht? Dan kunt u deze e-mail negeren.</p>"
        "<p>Met vriendelijke groet,<br>SanskritiSetu</p>"
    )
    return EmailMessage(to=to_email, subject=onderwerp, body=tekst, html_body=html_tekst)
