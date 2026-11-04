"""Billing & integrations domain registry (ADR-033 Laag 2, max 80 regels)."""

from fastapi import FastAPI
from loguru import logger


def register(app: FastAPI) -> int:
    """Register billing, webhook and integration routers. Returns count."""
    count = 0

    from src.core.api.v1.activepieces import domain_router as activepieces_domain_router
    from src.core.api.crag_endpoints import router as crag_router
    from src.core.api.evaluation_endpoints import router as evaluation_router
    from src.core.api.sandbox_endpoints import router as sandbox_router
    from src.core.api.search_endpoints import router as search_router
    from src.core.api.setup_endpoints import router as setup_router
    from src.core.api.usage_endpoints import router as usage_router
    from src.core.api.webhooks.activepieces_handler import router as activepieces_webhook
    from src.core.api.webhooks.telegram_handler import router as telegram_webhook
    from src.core.api.webhooks.whatsapp_handler import router as whatsapp_webhook
    from src.core.shared.config import is_setup_mode_enabled

    try:
        from src.core.api.billing_endpoints import router as billing_router
        from src.core.api.webhooks.stripe_handler import router as stripe_webhook

        app.include_router(billing_router, prefix="/api/v1", tags=["Billing"])
        count += 1
        app.include_router(stripe_webhook, prefix="/api/v1", tags=["Webhooks"])
        count += 1
    except (ImportError, ModuleNotFoundError) as e:
        logger.warning("Skipping billing/stripe routers: %s", e)
    except Exception as e:
        logger.error("Billing/stripe router registration failed: %s", e)
        raise

    app.include_router(usage_router, prefix="/api/v1", tags=["Usage"])
    count += 1
    app.include_router(search_router, prefix="/api/v1")
    count += 1
    app.include_router(evaluation_router, prefix="/api/v1")
    count += 1
    app.include_router(crag_router, prefix="/api/v1")
    count += 1
    app.include_router(telegram_webhook, prefix="/api/v1/webhooks", tags=["Webhooks"])
    count += 1
    app.include_router(whatsapp_webhook, prefix="/api/v1/webhooks", tags=["Webhooks"])
    count += 1
    app.include_router(activepieces_webhook, prefix="/api/v1", tags=["Webhooks"])
    count += 1
    if is_setup_mode_enabled():
        app.include_router(setup_router, prefix="/api/v1/setup", tags=["Setup"])
        count += 1
    app.include_router(sandbox_router, prefix="/api/v1", tags=["Sandbox"])
    count += 1
    app.include_router(activepieces_domain_router)
    count += 1

    logger.debug("integrations routers registered: %s", count)
    return count
