import logging
from typing import Any

from sqlalchemy import select

from src.core.database.database import db_manager
from src.core.middleware.tenant_context import set_tenant_id
from src.core.models.integration_models import TenantIntegration
from src.core.noodstop.weggegooid import registreer_weggegooid
from src.core.services.cva_service import CVAService
from src.core.services.messaging.gateway import ResponseGateway
from src.core.services.noodstop_toegang import KlantStilgezet, eis_klant_actief
from src.core.tasks.dramatiq_broker import workflow_actor
from src.core.tasks.eigen_loop import SessieFabriek, draai_in_eigen_loop

logger = logging.getLogger(__name__)

# Sentinel for external/anonymous users where no internal user_id is available.
# Used when callers (Telegram, WhatsApp) cannot resolve an internal user record.
_EXTERNAL_USER_SENTINEL = 0


@workflow_actor(queue_name="cva_queue")
def process_cva_message(
    request_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> None:  # TODO(TYPE): replace Any with concrete type
    """Sync wrapper -- thread-safe, geen AsyncIO middleware nodig.

    NOTE: draai_in_eigen_loop = asyncio.run (verse loop) + eigen poolloze engine (zie eigen_loop).
    Gebruik nooit asyncio.new_event_loop()+set_event_loop() in een actor --
    dat is niet thread-safe bij parallelle workers (CLAUDE.md valkuil).
    """
    draai_in_eigen_loop(lambda fabriek: _process_cva_message_async(request_data, fabriek))


async def _process_cva_message_async(
    request_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    sessie_fabriek: SessieFabriek,
) -> None:
    """Interne async implementatie -- nooit direct aanroepen.
    Dramatiq actor to process incoming CVA messages.
    """
    tenant_id = request_data.get("tenant_id")
    channel = request_data.get("channel")
    text = request_data.get("text")
    sender_id = request_data.get("sender_id")
    user_id_raw = request_data.get("user_id")

    # Validate required fields
    if not tenant_id:
        logger.error("Missing required field: tenant_id")
        return
    if not channel:
        logger.error("Missing required field: channel")
        return
    if text is None:
        logger.error("Missing required field: text")
        return

    try:
        set_tenant_id(int(tenant_id))

        # Resolve user_id: callers should provide a real user_id where available.
        # Falls back to _EXTERNAL_USER_SENTINEL (0) for anonymous/external senders.
        if user_id_raw is not None:
            try:
                user_id_int = int(user_id_raw)
            except (ValueError, TypeError):
                # Log type only -- user_id_raw may be PII (e.g. Telegram integer user ID).
                logger.warning(
                    "Invalid user_id type, using external sentinel: %s",
                    type(user_id_raw).__name__,
                )
                user_id_int = _EXTERNAL_USER_SENTINEL
        else:
            user_id_int = _EXTERNAL_USER_SENTINEL

        logger.info("Processing %s message for tenant %s", channel, tenant_id)

        # NOODSTOP PER KLANT (ADR-036 OP-03): deze actor is een deur -- hij laat de klantenservice-agent
        # antwoorden en stuurt dat naar een extern persoon (Telegram, WhatsApp). Een stilgezette klant
        # krijgt GEEN antwoord en er wordt niets gestuurd; het bericht gaat niet verloren in de
        # wachtrij maar wordt hier bewust niet beantwoord. Is de stand niet te lezen, dan gooien we door
        # (storing, een latere poging is dan juist goed).
        try:
            await eis_klant_actief(int(tenant_id))
        except KlantStilgezet as stop:
            if stop.onbekend:
                raise
            # Weggegooid, maar GETELD en gelogd (besluit C ronde 2): na het opheffen is zo
            # zichtbaar hoeveel berichten onbeantwoord bleven.
            await registreer_weggegooid(int(tenant_id), str(channel), sessie_fabriek)
            return

        await db_manager.initialize()  # al gedaan door de workerhook; sessies via eigen engine
        async with sessie_fabriek() as db:
            # 1. Fetch integration config
            stmt = select(TenantIntegration).where(
                TenantIntegration.tenant_id == tenant_id,
                TenantIntegration.channel_type == channel,
            )
            result = await db.execute(stmt)
            integration = result.scalar_one_or_none()

            if not integration:
                logger.warning(
                    "No integration found for tenant %s on channel %s", tenant_id, channel
                )
                return

            if not integration.is_active:
                logger.warning(
                    "Integration found but is INACTIVE for tenant %s on channel %s",
                    tenant_id,
                    channel,
                )
                return

            # 2. Call CVA Service
            cva_service = CVAService(db_session=db)

            try:
                response_data = await cva_service.chat(
                    message=text,
                    user_id=user_id_int,
                    tenant_id=int(tenant_id),
                )

                await db.flush()
                await db.commit()

                answer = response_data.get("response", "")
                assert isinstance(answer, str), "CVA response must be a string"

                # 3. Send response back via Gateway
                gateway = ResponseGateway()

                if channel == "telegram":
                    # Validate required fields for Telegram
                    bot_token = integration.bot_token
                    if not bot_token:
                        logger.error("Telegram bot_token is not configured")
                        return
                    if not sender_id:
                        logger.error("Missing sender_id for Telegram message")
                        return

                    await gateway.send_telegram_message(
                        bot_token=bot_token,
                        chat_id=int(sender_id),
                        text=answer,
                    )
                elif channel == "whatsapp_twilio":
                    config = integration.provider_config or {}

                    # Extract and validate required fields
                    account_sid = config.get("account_sid")
                    auth_token = config.get("auth_token")
                    from_number = config.get("from_number")

                    if not account_sid:
                        logger.error("Missing account_sid in WhatsApp provider config")
                        return
                    if not auth_token:
                        logger.error("Missing auth_token in WhatsApp provider config")
                        return
                    if not from_number:
                        logger.error("Missing from_number in WhatsApp provider config")
                        return
                    if not sender_id:
                        logger.error("Missing sender_id for WhatsApp message")
                        return

                    await gateway.send_whatsapp_message(
                        account_sid=str(account_sid),
                        auth_token=str(auth_token),
                        from_number=str(from_number),
                        to_number=str(sender_id),
                        text=answer,
                    )

                logger.info("Successfully processed and responded to %s message", channel)

            except Exception as e:
                logger.error("Error in CVA task: %s", e, exc_info=True)
                raise
    finally:
        set_tenant_id(None)
