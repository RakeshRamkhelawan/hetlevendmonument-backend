"""Brevo Transactional Email Service (ADR-029 P1-5).

Orchestrates transactional emails for the Foundation Portal:
- Magic link passwordless authentication
- Notice & Takedown receipt and status confirmations
- Newsletter opt-in and welcome messages
"""

from __future__ import annotations

import html
import logging

from src.core.connectors.brevo import BrevoClient, mask_email

logger = logging.getLogger(__name__)


class BrevoEmailService:
    """High-level transactional email service for Foundation Portal."""

    def __init__(self, client: BrevoClient | None = None) -> None:
        self.client = client or BrevoClient()

    @property
    def sent_emails(self) -> list[dict[str, object]]:
        """Sent emails in dev/test mode."""
        return self.client.sent_emails

    def clear_sent_emails(self) -> None:
        """Clear recorded emails for test isolation."""
        self.client.clear_sent_emails()

    async def send_transactional_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        to_name: str | None = None,
        tags: list[str] | None = None,
        reply_to: str | None = None,
    ) -> bool:
        """Send a generic transactional email."""
        masked = mask_email(to_email)
        try:
            await self.client.send_email(
                to_email=to_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                to_name=to_name,
                tags=tags,
                reply_to=reply_to,
            )
            return True
        except Exception as exc:
            logger.error(
                "send_transactional_email_failed: to=%s subject=%s error=%s",
                masked,
                subject,
                str(exc),
            )
            return False

    async def send_magic_link(
        self,
        to_email: str,
        magic_link_url: str,
        expires_in_minutes: int = 15,
        tenant_name: str | None = None,
    ) -> bool:
        """Send passwordless magic link email for portal authentication."""
        app_name = tenant_name or "Het Levend Monument"
        subject = f"Je magische inloglink voor {app_name}"
        safe_url = html.escape(magic_link_url)
        safe_app = html.escape(app_name)

        html_content = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8">
  <title>{safe_app} - Inloglink</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 24px;">
  <div style="background-color: #f8fafc; border-radius: 8px; padding: 24px; border: 1px solid #e2e8f0;">
    <h2 style="color: #0f172a; margin-top: 0;">Inloggen bij {safe_app}</h2>
    <p>Klik op de onderstaande knop om veilig in te loggen op het portaal:</p>
    <div style="text-align: center; margin: 28px 0;">
      <a href="{safe_url}" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Direct Inloggen</a>
    </div>
    <p style="font-size: 13px; color: #64748b;">
      Deze link is <strong>{expires_in_minutes} minuten</strong> geldig en kan eenmalig gebruikt worden.
    </p>
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
    <p style="font-size: 12px; color: #94a3b8;">
      Heb je deze inloglink niet zelf aangevraagd? Dan kun je deze e-mail veilig negeren.
    </p>
  </div>
</body>
</html>"""

        text_content = (
            f"Inloggen bij {app_name}\n\n"
            f"Gebruik deze link om in te loggen:\n{magic_link_url}\n\n"
            f"Deze link is {expires_in_minutes} minuten geldig.\n"
            f"Niet zelf aangevraagd? Negeer dan dit bericht."
        )

        return await self.send_transactional_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            tags=["portal-auth", "magic-link"],
        )

    async def send_takedown_confirmation(
        self,
        to_email: str,
        takedown_id: int,
        content_title: str,
        tenant_name: str | None = None,
    ) -> bool:
        """Send Notice & Takedown request confirmation to the requester."""
        app_name = tenant_name or "Het Levend Monument"
        subject = f"Bevestiging melding Notice & Takedown #{takedown_id} - {app_name}"
        safe_title = html.escape(content_title)
        safe_app = html.escape(app_name)

        html_content = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8">
  <title>{safe_app} - Melding #{takedown_id}</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 24px;">
  <div style="background-color: #f8fafc; border-radius: 8px; padding: 24px; border: 1px solid #e2e8f0;">
    <h2 style="color: #0f172a; margin-top: 0;">Ontvangstbevestiging Notice & Takedown</h2>
    <p>Wij hebben uw verzoek tot verwijdering of herbeoordeling in goede orde ontvangen.</p>
    <div style="background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 16px; margin: 16px 0;">
      <p style="margin: 0 0 8px 0;"><strong>Referentienummer:</strong> #{takedown_id}</p>
      <p style="margin: 0;"><strong>Betreft erfgoeditem:</strong> {safe_title}</p>
    </div>
    <p>
      Onze curatoren beoordelen uw melding binnen 24 tot 48 uur conform de Nederlandse Gedragscode Notice and Take Down.
      U ontvangt per e-mail bericht zodra de beoordeling is afgerond.
    </p>
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
    <p style="font-size: 12px; color: #94a3b8;">
      Dit is een geautomatiseerd bericht van {safe_app}.
    </p>
  </div>
</body>
</html>"""

        text_content = (
            f"Ontvangstbevestiging Notice & Takedown - {app_name}\n\n"
            f"Referentienummer: #{takedown_id}\n"
            f"Betreft erfgoeditem: {content_title}\n\n"
            f"Onze curatoren beoordelen uw melding binnen 24-48 uur conform de Nederlandse Gedragscode NTD.\n"
        )

        return await self.send_transactional_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            tags=["portal-takedown", f"ntd-{takedown_id}"],
        )

    async def send_takedown_resolution(
        self,
        to_email: str,
        takedown_id: int,
        content_title: str,
        status: str,
        resolution_note: str,
        tenant_name: str | None = None,
    ) -> bool:
        """Send Notice & Takedown resolution decision to requester (DSA Art. 16(5))."""
        app_name = tenant_name or "Het Levend Monument"
        status_nl = {
            "approved": "Toegewezen (Content verwijderd)",
            "rejected": "Afgewezen (Ongegrond verklaard)",
            "escalated": "In beraad (Geescaleerd naar bestuur)",
        }.get(status.lower(), status)

        subject = f"Besluit melding Notice & Takedown #{takedown_id} - {app_name}"
        safe_title = html.escape(content_title)
        safe_app = html.escape(app_name)
        safe_note = html.escape(resolution_note)
        safe_status = html.escape(status_nl)

        html_content = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8">
  <title>{safe_app} - Besluit Melding #{takedown_id}</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 24px;">
  <div style="background-color: #f8fafc; border-radius: 8px; padding: 24px; border: 1px solid #e2e8f0;">
    <h2 style="color: #0f172a; margin-top: 0;">Besluit Notice & Takedown Melding</h2>
    <p>Onze curatoren hebben uw melding onderzocht en beoordeeld conform de Nederlandse Gedragscode Notice and Take Down en de Digital Services Act (DSA Art. 16).</p>
    <div style="background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 16px; margin: 16px 0;">
      <p style="margin: 0 0 8px 0;"><strong>Referentienummer:</strong> #{takedown_id}</p>
      <p style="margin: 0 0 8px 0;"><strong>Erfgoeditem:</strong> {safe_title}</p>
      <p style="margin: 0;"><strong>Besluit:</strong> {safe_status}</p>
    </div>
    <div style="background-color: #ffffff; border-left: 4px solid #3b82f6; padding: 12px 16px; margin: 16px 0;">
      <p style="margin: 0 0 4px 0; font-weight: bold; font-size: 13px; color: #475569;">Motivering van de curator:</p>
      <p style="margin: 0; font-size: 14px; white-space: pre-wrap;">{safe_note}</p>
    </div>
    <p style="font-size: 13px; color: #64748b;">
      Indien u nadere vragen heeft of bezwaar wenst te maken tegen dit besluit, kunt u contact opnemen via ons contactformulier onder vermelding van referentienummer #{takedown_id}.
    </p>
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
    <p style="font-size: 12px; color: #94a3b8;">
      Dit is een officiele kennisgeving van {safe_app} conform artikel 16 lid 5 van de Digital Services Act (Verordening EU 2022/2065).
    </p>
  </div>
</body>
</html>"""

        text_content = (
            f"Besluit Notice & Takedown Melding - {app_name}\n\n"
            f"Referentienummer: #{takedown_id}\n"
            f"Erfgoeditem: {content_title}\n"
            f"Besluit: {status_nl}\n\n"
            f"Motivering van de curator:\n{resolution_note}\n\n"
            f"Voor vragen of bezwaar kunt u contact opnemen onder vermelding van referentienummer #{takedown_id}.\n"
        )

        return await self.send_transactional_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            tags=["portal-takedown", f"ntd-resolution-{takedown_id}"],
        )

    async def send_takedown_uploader_notice(
        self,
        to_email: str,
        takedown_id: int,
        content_title: str,
        resolution_note: str,
        tenant_name: str | None = None,
    ) -> bool:
        """Send takedown notification to uploader with 14-day objection option."""
        app_name = tenant_name or "Het Levend Monument"
        subject = f"Kennisgeving offline halen erfgoeditem #{takedown_id} - {app_name}"
        safe_title = html.escape(content_title)
        safe_app = html.escape(app_name)
        safe_note = html.escape(resolution_note)

        html_content = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8">
  <title>{safe_app} - Kennisgeving Verwijdering</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 24px;">
  <div style="background-color: #f8fafc; border-radius: 8px; padding: 24px; border: 1px solid #e2e8f0;">
    <h2 style="color: #0f172a; margin-top: 0;">Kennisgeving van Verwijdering</h2>
    <p>Naar aanleiding van een melding van inbreuk (Notice & Takedown) is uw ingediende erfgoeditem tijdelijk offline gehaald.</p>
    <div style="background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 16px; margin: 16px 0;">
      <p style="margin: 0 0 8px 0;"><strong>Erfgoeditem:</strong> {safe_title}</p>
      <p style="margin: 0 0 8px 0;"><strong>Referentienummer melding:</strong> #{takedown_id}</p>
      <p style="margin: 0;"><strong>Reden:</strong> {safe_note}</p>
    </div>
    <p>
      Indien u van mening bent dat deze verwijdering onterecht is (bijvoorbeeld omdat u aantoonbaar over de juiste auteursrechten of toestemming beschikt), kunt u binnen 14 dagen bezwaar indienen via ons contactformulier onder vermelding van referentienummer #{takedown_id}.
    </p>
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
    <p style="font-size: 12px; color: #94a3b8;">
      Dit is een geautomatiseerd bericht van {safe_app} conform de Nederlandse Gedragscode Notice and Take Down.
    </p>
  </div>
</body>
</html>"""

        text_content = (
            f"Kennisgeving van Verwijdering - {app_name}\n\n"
            f"Uw erfgoeditem '{content_title}' is tijdelijk offline gehaald naar aanleiding van melding #{takedown_id}.\n\n"
            f"Reden: {resolution_note}\n\n"
            f"U kunt binnen 14 dagen bezwaar aantekenen via ons contactformulier.\n"
        )

        return await self.send_transactional_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            tags=["portal-takedown", f"ntd-uploader-{takedown_id}"],
        )

    async def send_newsletter_optin_request(
        self,
        to_email: str,
        confirm_url: str,
        tenant_name: str | None = None,
    ) -> bool:
        """Send double opt-in confirmation request email for newsletter subscription."""
        app_name = tenant_name or "Het Levend Monument"
        subject = f"Bevestig uw inschrijving voor de nieuwsbrief van {app_name}"
        safe_app = html.escape(app_name)
        safe_confirm = html.escape(confirm_url)

        html_content = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8">
  <title>{safe_app} - Bevestig uw inschrijving</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 24px;">
  <div style="background-color: #f8fafc; border-radius: 8px; padding: 24px; border: 1px solid #e2e8f0;">
    <h2 style="color: #0f172a; margin-top: 0;">Bevestig uw inschrijving</h2>
    <p>Bedankt voor uw interesse in de nieuwsbrief van {safe_app}.</p>
    <p>Om te verifieren dat dit e-mailadres van u is en om uw inschrijving te voltooien, klikt u op onderstaande knop:</p>
    <div style="text-align: center; margin: 28px 0;">
      <a href="{safe_confirm}" style="display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; font-size: 16px;">Inschrijving bevestigen</a>
    </div>
    <p style="font-size: 13px; color: #64748b;">
      Werkt de knop niet? Kopieer en plak de volgende URL in uw browser:<br>
      <a href="{safe_confirm}" style="color: #2563eb; word-break: break-all;">{safe_confirm}</a>
    </p>
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
    <p style="font-size: 12px; color: #94a3b8;">
      Heeft u zich niet aangemeld voor de nieuwsbrief? Dan kunt u deze e-mail veilig negeren. Er worden geen verdere berichten verstuurd zonder bevestiging.
    </p>
  </div>
</body>
</html>"""

        text_content = (
            f"Bevestig uw inschrijving voor de nieuwsbrief van {app_name}\n\n"
            f"Klik op onderstaande link om uw inschrijving te bevestigen:\n{confirm_url}\n\n"
            f"Heeft u zich niet aangemeld? Dan kunt u dit bericht veilig negeren.\n"
        )

        return await self.send_transactional_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            tags=["portal-newsletter", "double-opt-in"],
        )

    async def send_newsletter_confirmation(
        self,
        to_email: str,
        confirm_url: str | None = None,
        unsubscribe_url: str | None = None,
        tenant_name: str | None = None,
    ) -> bool:
        """Send newsletter welcome/confirmation email."""
        app_name = tenant_name or "Het Levend Monument"
        subject = f"Welkom bij de nieuwsbrief van {app_name}"
        safe_app = html.escape(app_name)

        unsub_block = ""
        if unsubscribe_url:
            safe_unsub = html.escape(unsubscribe_url)
            unsub_block = f'<p style="font-size: 12px; color: #94a3b8;">Uitschrijven kan op elk gewenst moment via <a href="{safe_unsub}" style="color: #64748b;">deze link</a>.</p>'

        html_content = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8">
  <title>{safe_app} - Nieuwsbrief</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 24px;">
  <div style="background-color: #f8fafc; border-radius: 8px; padding: 24px; border: 1px solid #e2e8f0;">
    <h2 style="color: #0f172a; margin-top: 0;">Bedankt voor uw inschrijving!</h2>
    <p>U bent succesvol ingeschreven voor updates en verhalen van {safe_app}.</p>
    <p>U ontvangt periodiek onze nieuwsbrief met nieuwe historische inzendingen en educatieve programma's.</p>
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
    {unsub_block}
  </div>
</body>
</html>"""

        text_content = (
            f"Bedankt voor uw inschrijving bij de nieuwsbrief van {app_name}!\n\n"
            f"U ontvangt periodiek updates over nieuw erfgoed.\n"
            + (f"\nUitschrijven: {unsubscribe_url}\n" if unsubscribe_url else "")
        )

        return await self.send_transactional_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            tags=["portal-newsletter"],
        )

    async def send_contact_confirmation(
        self,
        to_email: str,
        reference_id: str,
        sender_name: str,
        subject: str,
        tenant_name: str | None = None,
    ) -> bool:
        """Send contact inquiry confirmation to the submitter."""
        app_name = tenant_name or "Het Levend Monument"
        mail_subject = f"Ontvangstbevestiging contactverzoek [{reference_id}] - {app_name}"
        safe_name = html.escape(sender_name)
        safe_subject = html.escape(subject)
        safe_app = html.escape(app_name)
        safe_ref = html.escape(reference_id)

        html_content = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8">
  <title>{safe_app} - Contactverzoek {safe_ref}</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 24px;">
  <div style="background-color: #f8fafc; border-radius: 8px; padding: 24px; border: 1px solid #e2e8f0;">
    <h2 style="color: #0f172a; margin-top: 0;">Hartelijk dank voor uw bericht, {safe_name}</h2>
    <p>Wij hebben uw contactverzoek in goede orde ontvangen.</p>
    <div style="background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 16px; margin: 16px 0;">
      <p style="margin: 0 0 8px 0;"><strong>Referentienummer:</strong> {safe_ref}</p>
      <p style="margin: 0;"><strong>Onderwerp:</strong> {safe_subject}</p>
    </div>
    <p>
      Het team van {safe_app} streeft ernaar uw vraag of melding binnen enkele werkdagen te beantwoorden.
    </p>
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
    <p style="font-size: 12px; color: #94a3b8;">
      Dit is een geautomatiseerde ontvangstbevestiging van {safe_app}.
    </p>
  </div>
</body>
</html>"""

        text_content = (
            f"Beste {sender_name},\n\n"
            f"Hartelijk dank voor uw bericht aan {app_name}.\n\n"
            f"Referentienummer: {reference_id}\n"
            f"Onderwerp: {subject}\n\n"
            f"Wij streven ernaar binnen enkele werkdagen contact met u op te nemen.\n\n"
            f"Met vriendelijke groet,\n{app_name}"
        )

        return await self.send_transactional_email(
            to_email=to_email,
            subject=mail_subject,
            html_content=html_content,
            text_content=text_content,
            tags=["portal-contact", "confirmation", reference_id.lower()],
        )

    async def send_contact_notification(
        self,
        to_email: str,
        reference_id: str,
        sender_name: str,
        sender_email: str,
        subject: str,
        category: str,
        message: str,
        tenant_name: str | None = None,
    ) -> bool:
        """Send contact inquiry notification to foundation curator/admin."""
        app_name = tenant_name or "Het Levend Monument"
        mail_subject = f"Nieuw contactbericht [{category.upper()}]: {subject} ({reference_id})"
        safe_name = html.escape(sender_name)
        safe_email = html.escape(sender_email)
        safe_subject = html.escape(subject)
        safe_category = html.escape(category)
        safe_message = html.escape(message).replace("\n", "<br>")
        safe_app = html.escape(app_name)
        safe_ref = html.escape(reference_id)

        html_content = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8">
  <title>{safe_app} - Nieuw contactbericht</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 24px;">
  <div style="background-color: #f8fafc; border-radius: 8px; padding: 24px; border: 1px solid #e2e8f0;">
    <h2 style="color: #0f172a; margin-top: 0;">Nieuw binnengekomen contactbericht</h2>
    <p>Er is een nieuw contactverzoek ingediend op {safe_app}:</p>
    <div style="background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 16px; margin: 16px 0;">
      <p style="margin: 0 0 6px 0;"><strong>Referentie:</strong> {safe_ref}</p>
      <p style="margin: 0 0 6px 0;"><strong>Categorie:</strong> {safe_category}</p>
      <p style="margin: 0 0 6px 0;"><strong>Naam afzender:</strong> {safe_name}</p>
      <p style="margin: 0 0 6px 0;"><strong>E-mailadres:</strong> <a href="mailto:{safe_email}">{safe_email}</a></p>
      <p style="margin: 0 0 12px 0;"><strong>Onderwerp:</strong> {safe_subject}</p>
      <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 12px 0;">
      <p style="margin: 0; white-space: pre-wrap;">{safe_message}</p>
    </div>
    <div style="text-align: center; margin: 20px 0;">
      <a href="mailto:{safe_email}?subject=Re:%20[{safe_ref}]%20{safe_subject}" style="background-color: #0f172a; color: #ffffff; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Reageer per E-mail</a>
    </div>
  </div>
</body>
</html>"""

        text_content = (
            f"Nieuw contactbericht [{category.upper()}] - {app_name}\n\n"
            f"Referentie: {reference_id}\n"
            f"Van: {sender_name} <{sender_email}>\n"
            f"Onderwerp: {subject}\n"
            f"Categorie: {category}\n\n"
            f"Bericht:\n{message}\n"
        )

        return await self.send_transactional_email(
            to_email=to_email,
            subject=mail_subject,
            html_content=html_content,
            text_content=text_content,
            tags=["portal-contact", "notification", category.lower()],
            reply_to=sender_email,
        )

    async def send_curation_rejection_notification(
        self,
        to_email: str,
        content_title: str,
        rejection_reason: str,
        to_name: str | None = None,
        tenant_name: str | None = None,
        redress_email: str | None = None,
    ) -> bool:
        """Send DSA Art. 17 statement of reasons notification when content is rejected."""
        app_name = tenant_name or "Het Levend Monument"
        subject = f"Besluit over je ingezonden bijdrage: '{content_title}' - {app_name}"
        contact_for_redress = redress_email or "curator@erfgoed.org"

        safe_title = html.escape(content_title)
        safe_reason = html.escape(rejection_reason).replace("\n", "<br>")
        safe_name = html.escape(to_name or "Beste inzender")
        safe_app = html.escape(app_name)
        safe_redress = html.escape(contact_for_redress)

        html_content = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8">
  <title>{safe_app} - Bericht over je bijdrage</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 24px;">
  <div style="background-color: #f8fafc; border-radius: 8px; padding: 24px; border: 1px solid #e2e8f0;">
    <h2 style="color: #0f172a; margin-top: 0;">Besluit over je ingezonden bijdrage</h2>
    <p>{safe_name},</p>
    <p>Bedankt voor je betrokkenheid bij {safe_app}. De redactie heeft je inzending <strong>'{safe_title}'</strong> beoordeeld.</p>
    <p>Helaas kan deze bijdrage in de huidige vorm niet worden gepubliceerd op het platform.</p>
    <div style="background-color: #ffffff; border-left: 4px solid #ef4444; padding: 14px 18px; margin: 20px 0; border-radius: 0 6px 6px 0;">
      <p style="margin: 0 0 6px 0; font-weight: bold; color: #991b1b;">Motivering van het besluit (DSA Art. 17):</p>
      <p style="margin: 0; color: #334155;">{safe_reason}</p>
    </div>
    <div style="background-color: #f1f5f9; border-radius: 6px; padding: 14px 18px; margin: 20px 0; font-size: 13px; color: #475569;">
      <p style="margin: 0 0 6px 0; font-weight: bold;">Bezwaar en heroverweging:</p>
      <p style="margin: 0;">Ben je van mening dat dit besluit onterecht is genomen? Conform de Digital Services Act (DSA Art. 17 & 20) heb je het recht om bezwaar te maken. Neem binnen 6 maanden contact op via <a href="mailto:{safe_redress}">{safe_redress}</a> met vermelding van de titel van je bijdrage.</p>
    </div>
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
    <p style="font-size: 12px; color: #94a3b8; margin: 0;">
      Dit is een geautomatiseerd servicebericht van {safe_app}.
    </p>
  </div>
</body>
</html>"""

        text_content = (
            f"Besluit over je ingezonden bijdrage - {app_name}\n\n"
            f"{to_name or 'Beste inzender'},\n\n"
            f"De redactie heeft je inzending '{content_title}' beoordeeld. Helaas kan deze "
            f"bijdrage niet worden gepubliceerd.\n\n"
            f"Motivering (DSA Art. 17):\n{rejection_reason}\n\n"
            f"Bezwaar maken: Neem binnen 6 maanden contact op via {contact_for_redress}.\n"
        )

        return await self.send_transactional_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            tags=["curation-rejection", "dsa-art17"],
        )


# Global singleton service
brevo_email_service = BrevoEmailService()
