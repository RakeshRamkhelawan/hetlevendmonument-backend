"""Webhooks FastAPI dependencies (ADR-033)."""

from src.core.database.database import get_db as get_db
from src.core.database.tenant_query_filter import TenantFilterBypass as TenantFilterBypass
from src.core.governance.audit import AuditService as AuditService
from src.core.governance.models import AuditLog as AuditLog
from src.core.services.messaging.telegram import TelegramGateway as TelegramGateway
from src.core.services.messaging.whatsapp import WhatsAppGateway as WhatsAppGateway
from src.core.services.subscription_cache import TenantSubscriptionCache as TenantSubscriptionCache

__all__ = [
    "AuditLog",
    "AuditService",
    "TelegramGateway",
    "TenantFilterBypass",
    "TenantSubscriptionCache",
    "WhatsAppGateway",
    "get_db",
]
