"""
SC-10.2: Email Templates with Jinja2
Provides HTML email template rendering with Jinja2.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: De map met de mailsjablonen: de ENIGE plek. `services/email.py` (TEMPLATE_DIR) gebruikt dezelfde.
#: Hij staat onder `src/` omdat de Dockerfile alleen `src/`, `config/` en `scripts/` meeneemt; de zes
#: sjablonen stonden tot 2026-10-15 in `templates/email/` in de root, waar de engine nooit zocht en waar
#: elke mail daardoor op de terugvaloptie (een dump van de context) uitkwam.
STANDAARD_SJABLONENMAP = Path(__file__).resolve().parent.parent / "templates" / "email"

# Try to import Jinja2
try:
    import jinja2  # noqa: F401, type: ignore

    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False


@dataclass
class RenderedEmail:
    """Represents a rendered email."""

    subject: str
    html_body: str
    text_body: str | None = None


class EmailTemplateEngine:
    """
    SC-10.2: Jinja2-based email template engine.

    Renders HTML and text email templates with variable substitution.
    """

    def __init__(self, templates_dir: str | None = None) -> None:
        if not JINJA2_AVAILABLE:
            logger.warning("Jinja2 not installed. Email templates disabled.")
            self.env = None
            return

        from jinja2 import Environment, FileSystemLoader, select_autoescape

        templates_dir = templates_dir or str(STANDAARD_SJABLONENMAP)

        # Create templates directory if it doesn't exist
        Path(templates_dir).mkdir(parents=True, exist_ok=True)

        self.env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Add custom filters
        self.env.filters["format_date"] = self._format_date
        self.env.filters["format_currency"] = self._format_currency

        logger.info(f"Email template engine initialized: {templates_dir}")

    def render(
        self, template_name: str, subject: str, context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> RenderedEmail:
        """
        Render an email template.

        Args:
            template_name: Name of the template file (e.g., "welcome.html")
            subject: Email subject line
            context: Variables to pass to the template

        Returns:
            RenderedEmail with subject and body
        """
        if not self.env:
            return self._fallback_render(template_name, subject, context or {})

        context = context or {}

        # Add default context
        context.setdefault("app_name", "SanskritiSetu")
        context.setdefault("support_email", "support@sanskriti.org")
        context.setdefault("year", "2025")

        try:
            # Render HTML template
            html_template = self.env.get_template(template_name)
            html_body = html_template.render(**context)

            # Try to render text version
            text_body = None
            text_template_name = template_name.replace(".html", ".txt")
            try:
                text_template = self.env.get_template(text_template_name)
                text_body = text_template.render(**context)
            except Exception:
                pass

            return RenderedEmail(subject=subject, html_body=html_body, text_body=text_body)

        except Exception as e:
            logger.error(f"Template rendering failed: {e}")
            return self._fallback_render(template_name, subject, context)

    def _fallback_render(
        self, template_name: str, subject: str, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> RenderedEmail:
        """Fallback when Jinja2 is not available."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>{subject}</title></head>
        <body>
            <h1>{subject}</h1>
            <p>Template: {template_name}</p>
            <p>Context: {context}</p>
        </body>
        </html>
        """
        return RenderedEmail(subject=subject, html_body=html)

    @staticmethod
    def _format_date(value: Any, format: str = "%B %d, %Y") -> str:  # TODO(TYPE): replace Any with concrete type
        """Format a date for display."""
        if hasattr(value, "strftime"):
            # Type narrowing: confirmed value has strftime method
            result: str = value.strftime(format)
            return result
        return str(value)

    @staticmethod
    def _format_currency(value: Any, currency: str = "EUR") -> str:  # TODO(TYPE): replace Any with concrete type
        """Format a number as currency."""
        symbols = {"EUR": "euro", "USD": "$", "GBP": "pound"}
        symbol = symbols.get(currency, currency)
        return f"{symbol}{value:,.2f}"


# Pre-defined email templates as strings (for creating default templates)
DEFAULT_TEMPLATES = {
    "welcome.html": """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }
        .content { padding: 30px; background: #f9f9f9; }
        .button { display: inline-block; padding: 12px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; }
        .footer { padding: 20px; text-align: center; color: #666; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Welcome to {{ app_name }}!</h1>
        </div>
        <div class="content">
            <p>Hello {{ user_name }},</p>
            <p>Thank you for joining {{ app_name }}! We're excited to have you on board.</p>
            <p>To get started, please verify your email address:</p>
            <p style="text-align: center;">
                <a href="{{ verification_url }}" class="button">Verify Email</a>
            </p>
            <p>If you didn't create this account, you can safely ignore this email.</p>
        </div>
        <div class="footer">
            <p>&copy; {{ year }} {{ app_name }}. All rights reserved.</p>
            <p>Questions? Contact us at {{ support_email }}</p>
        </div>
    </div>
</body>
</html>
""",
    "password_reset.html": """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #e74c3c; color: white; padding: 30px; text-align: center; }
        .content { padding: 30px; background: #f9f9f9; }
        .button { display: inline-block; padding: 12px 30px; background: #e74c3c; color: white; text-decoration: none; border-radius: 5px; }
        .footer { padding: 20px; text-align: center; color: #666; font-size: 12px; }
        .warning { background: #fff3cd; border: 1px solid #ffc107; padding: 15px; margin: 20px 0; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Password Reset Request</h1>
        </div>
        <div class="content">
            <p>Hello {{ user_name }},</p>
            <p>We received a request to reset your password. Click the button below to set a new password:</p>
            <p style="text-align: center;">
                <a href="{{ reset_url }}" class="button">Reset Password</a>
            </p>
            <div class="warning">
                <strong>Note:</strong> This link will expire in {{ expiry_hours }} hours.
            </div>
            <p>If you didn't request this, please ignore this email or contact support if you have concerns.</p>
        </div>
        <div class="footer">
            <p>&copy; {{ year }} {{ app_name }}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
""",
    "notification.html": """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .content { padding: 30px; background: #f9f9f9; border-left: 4px solid #667eea; }
        .footer { padding: 20px; text-align: center; color: #666; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="content">
            <h2>{{ title }}</h2>
            <p>{{ message }}</p>
            {% if action_url %}
            <p><a href="{{ action_url }}">{{ action_text | default("View Details") }}</a></p>
            {% endif %}
        </div>
        <div class="footer">
            <p>&copy; {{ year }} {{ app_name }}</p>
        </div>
    </div>
</body>
</html>
""",
}


def create_default_templates(templates_dir: str | None = None) -> None:
    """Create default email templates."""
    templates_dir = templates_dir or str(STANDAARD_SJABLONENMAP)

    Path(templates_dir).mkdir(parents=True, exist_ok=True)

    for name, content in DEFAULT_TEMPLATES.items():
        path = Path(templates_dir) / name
        if not path.exists():
            path.write_text(content.strip())
            logger.info(f"Created template: {name}")


# Singleton instance
email_templates = EmailTemplateEngine()
