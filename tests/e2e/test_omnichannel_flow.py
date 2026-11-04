import os
import uuid

# Set environment for testing - MUST BE DONE BEFORE IMPORTS
os.environ["RUN_E2E_TESTS"] = "true"
os.environ["ENVIRONMENT"] = "development"
# Respect the externally-set DATABASE_URL (E2E DB) instead of overriding it
pass

# LLM env vars are set/cleaned per-fixture to avoid cross-test contamination.
# Store originals so teardown can restore them.
_LLM_ENV_KEYS = ["LLM_MODEL", "LLM_PROVIDER", "LLM_API_KEY"]
_LLM_ORIGINALS: dict[str, str | None] = {k: os.environ.get(k) for k in _LLM_ENV_KEYS}

import asyncio

import httpx
import pytest
from sqlalchemy import delete, select, text

from src.core.conversations.models import Conversation, ConversationMessage
from src.core.database.database import db_manager
from src.core.models.integration_models import TenantIntegration
from src.core.models.rbac_models import Tenant, User


@pytest.fixture(scope="function")
async def test_tenant():
    # Set LLM env vars for this test only; restore originals in teardown
    os.environ["LLM_MODEL"] = "gemini-1.5-flash"
    os.environ["LLM_PROVIDER"] = "gemini"
    os.environ["LLM_API_KEY"] = "fake-test-key-for-e2e"

    # Force re-initialization to avoid closed event loop issues in multi-test runs
    db_manager._initialized = False
    await db_manager.initialize()

    # Skip if required tables are missing in the E2E database
    async with db_manager.get_session() as check_db:
        required_tables = ["conversations", "conversation_messages", "tenant_integrations"]
        for table in required_tables:
            result = await check_db.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :table)"
                ),
                {"table": table},
            )
            if not result.scalar():
                pytest.skip(f"Required table '{table}' missing in E2E database")

    test_user_id = None
    async with db_manager.get_session() as db:
        # Create a test tenant using only columns that exist in the DB schema.
        # max_users/max_agents/max_storage_gb are NOT NULL with no DB-side default
        # (the defaults in TenantCreate only apply on the ORM/Pydantic path), so a
        # raw INSERT must name them explicitly -- otherwise NotNullViolationError.
        _uid = uuid.uuid4().hex[:8]
        result = await db.execute(
            text(
                "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
                "VALUES (:name, :slug, :is_active, :max_users, :max_agents, :max_storage_gb) RETURNING id"
            ),
            {
                "name": f"E2E Test Tenant {_uid}",
                "slug": f"e2e-test-tenant-{_uid}",
                "is_active": True,
                "max_users": 10,
                "max_agents": 50,
                "max_storage_gb": 5,
            },
        )
        tenant_id = result.scalar_one()

        # Add Integration config
        integration = TenantIntegration(
            tenant_id=tenant_id,
            channel_type="telegram",
            bot_token="test_bot_123",
            webhook_secret="secret_token_123",
            is_active=True,
        )
        db.add(integration)

        # Add a test user with a unique ID (avoid PK conflicts)
        # Find a safe user id by querying the max existing id
        result = await db.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM users"))
        next_user_id = result.scalar()
        test_user_id = next_user_id
        user = User(
            email=f"e2e-worker-{uuid.uuid4().hex[:8]}@sanskritisetu.local",
            hashed_password="...",
            tenant_id=tenant_id,
            is_active=True,
            id=test_user_id,
        )
        db.add(user)

        await db.commit()

        yield tenant_id

        # Cleanup
        async with db_manager.get_session() as db_cleanup:
            await db_cleanup.execute(
                delete(TenantIntegration).where(TenantIntegration.tenant_id == tenant_id)
            )
            subq = select(Conversation.id).where(Conversation.tenant_id == tenant_id)
            await db_cleanup.execute(
                delete(ConversationMessage).where(ConversationMessage.conversation_id.in_(subq))
            )
            await db_cleanup.execute(
                delete(Conversation).where(Conversation.tenant_id == tenant_id)
            )
            if test_user_id is not None:
                await db_cleanup.execute(delete(User).where(User.id == test_user_id))
            await db_cleanup.execute(delete(Tenant).where(Tenant.id == tenant_id))
            await db_cleanup.commit()

        # Restore original LLM env vars to prevent cross-test contamination
        for key in _LLM_ENV_KEYS:
            orig = _LLM_ORIGINALS[key]
            if orig is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = orig


@pytest.mark.asyncio
class TestOmnichannelE2E:
    """
    End-to-End Test for the Omnichannel AI Gateway.
    """

    @pytest.mark.e2e
    async def test_telegram_to_ai_flow(self, test_tenant):
        from unittest.mock import AsyncMock, MagicMock, patch

        from httpx import ASGITransport

        # create_app() in test context (PYTEST_CURRENT_TEST set) skips register_all_routers,
        # so every path returns 404. create_test_app() explicitly calls register_all_routers.
        from src.main import create_test_app

        app = create_test_app()
        tenant_id = test_tenant

        # Patch the Telegram token validation (production code uses env var,
        # not the DB webhook_secret -- known limitation)
        os.environ["TELEGRAM_BOT_SECRET_TOKEN"] = "secret_token_123"

        try:
            # 1. Simulate incoming Telegram Webhook using the app directly
            # Patch the Dramatiq task send (requires running broker)
            # WHY here and not on src.core.services.messaging.telegram: that module no
            # longer imports process_cva_message (it takes enqueue_fn as a constructor
            # arg). The name lives at the call site,
            # src.core.api.webhooks.telegram_handler, which does
            # `from src.core.tasks.cva_tasks import process_cva_message` and passes
            # `process_cva_message.send` into TelegramGateway.
            with patch("src.core.api.webhooks.telegram_handler.process_cva_message") as mock_task:
                mock_task.send = MagicMock()

                transport = ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    payload = {
                        "update_id": 999,
                        "message": {
                            "message_id": 101,
                            "from": {"id": 12345, "first_name": "E2E User"},
                            "chat": {"id": 12345, "type": "private"},
                            "text": "Wat is de hoofdstad van Nederland?",
                        },
                    }
                    headers = {"X-Telegram-Bot-Api-Secret-Token": "secret_token_123"}

                    response = await client.post(
                        f"/api/v1/webhooks/telegram/{tenant_id}/test_bot_123",
                        json=payload,
                        headers=headers,
                    )

                    assert response.status_code == 200
                    assert response.json()["status"] == "ok"

            # 2. Run the worker logic manually
            from src.core.middleware.tenant_context import set_tenant_id
            from src.core.tasks.cva_tasks import process_cva_message

            # Set tenant context so the query filter doesn't block queries
            set_tenant_id(tenant_id)

            task_data = {
                "tenant_id": tenant_id,
                "channel": "telegram",
                "text": "Wat is de hoofdstad van Nederland?",
                "sender_id": "12345",
            }

            with pytest.MonkeyPatch().context() as mp:
                mp.setattr(
                    "src.core.services.messaging.gateway.ResponseGateway.send_telegram_message",
                    AsyncMock(return_value=True),
                )
                mp.setattr(
                    "src.core.services.messaging.gateway.ResponseGateway.send_whatsapp_message",
                    AsyncMock(return_value=True),
                )

                # MOCK THE LLM CALL
                from src.core.services.llm.service import LLMService

                mp.setattr(
                    LLMService,
                    "generate",
                    AsyncMock(
                        return_value=(
                            "De hoofdstad van Nederland is Amsterdam.",
                            {"total_tokens": 10, "model": "gemini-1.5-flash"},
                        )
                    ),
                )

                await process_cva_message.fn.__wrapped__(task_data)

            # 3. Verify DB entries
            async with db_manager.get_session() as db:
                stmt = select(Conversation).where(Conversation.tenant_id == tenant_id)
                result = await db.execute(stmt)
                convs = result.scalars().all()

                if len(convs) > 0:
                    conv = convs[0]
                    stmt = select(ConversationMessage).where(
                        ConversationMessage.conversation_id == conv.id
                    )
                    result = await db.execute(stmt)
                    messages = result.scalars().all()

                    assert len(messages) >= 2
                    assistant_msg = next(m for m in messages if m.role == "assistant")
                    print(f"Assistant Telegram E2E Response: {assistant_msg.content}")
                else:
                    pytest.fail("No conversation created for Telegram.")
        finally:
            os.environ.pop("TELEGRAM_BOT_SECRET_TOKEN", None)

    @pytest.mark.e2e
    async def test_whatsapp_to_ai_flow(self, test_tenant):
        from unittest.mock import AsyncMock, MagicMock, patch

        from httpx import ASGITransport

        # create_app() in test context (PYTEST_CURRENT_TEST set) skips register_all_routers,
        # so every path returns 404. create_test_app() explicitly calls register_all_routers.
        from src.main import create_test_app

        app = create_test_app()
        tenant_id = test_tenant

        # 1. Add WhatsApp Integration to DB
        async with db_manager.get_session() as db:
            integration = TenantIntegration(
                tenant_id=tenant_id,
                channel_type="whatsapp_twilio",
                is_active=True,
                provider_config={
                    "account_sid": "AC_TEST",
                    "auth_token": "token_TEST",
                    "from_number": "whatsapp:+14155238886",
                },
            )
            db.add(integration)
            await db.commit()

        # 2. Simulate incoming Twilio Webhook
        # Patch Twilio signature validation (production code uses env var TWILIO_AUTH_TOKEN)
        # and Dramatiq task send (requires running broker)
        with (
            patch(
                "src.core.services.messaging.whatsapp.WhatsAppGateway.validate_signature",
                new_callable=AsyncMock,
                return_value=True,
            ),
            # WHY the second patch targets whatsapp_handler, not messaging.whatsapp: that
            # module no longer imports process_cva_message (it takes enqueue_fn as a
            # constructor arg). The name lives at the call site,
            # src.core.api.webhooks.whatsapp_handler, which does
            # `from src.core.tasks.cva_tasks import process_cva_message` and passes
            # `process_cva_message.send` into WhatsAppGateway.
            patch("src.core.api.webhooks.whatsapp_handler.process_cva_message") as mock_task,
        ):
            mock_task.send = MagicMock()

            transport = ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                payload = {
                    "MessageSid": "SM_WHATSAPP_TEST",
                    "From": "whatsapp:+31612345678",
                    "To": "whatsapp:+14155238886",
                    "Body": "Wat is de hoofdstad van Frankrijk?",
                    "NumMedia": "0",
                }
                headers = {"X-Twilio-Signature": "valid_twilio_sig"}

                response = await client.post(
                    f"/api/v1/webhooks/whatsapp/twilio/{tenant_id}", data=payload, headers=headers
                )

                assert response.status_code == 200

        # 3. Run worker logic manually
        from src.core.middleware.tenant_context import set_tenant_id
        from src.core.tasks.cva_tasks import process_cva_message

        # Set tenant context so the query filter doesn't block queries
        set_tenant_id(tenant_id)

        task_data = {
            "tenant_id": tenant_id,
            "channel": "whatsapp_twilio",
            "text": "Wat is de hoofdstad van Frankrijk?",
            "sender_id": "whatsapp:+31612345678",
        }

        with pytest.MonkeyPatch().context() as mp:
            from unittest.mock import AsyncMock

            mp.setattr(
                "src.core.services.messaging.gateway.ResponseGateway.send_whatsapp_message",
                AsyncMock(return_value=True),
            )
            from src.core.services.llm.service import LLMService

            mp.setattr(
                LLMService,
                "generate",
                AsyncMock(
                    return_value=(
                        "De hoofdstad van Frankrijk is Parijs.",
                        {"total_tokens": 12, "model": "gemini-1.5-flash"},
                    )
                ),
            )

            await process_cva_message.fn.__wrapped__(task_data)

        # 4. Verify DB entries
        async with db_manager.get_session() as db:
            stmt = select(Conversation).where(
                Conversation.tenant_id == tenant_id, Conversation.agent_id == "cva"
            )
            result = await db.execute(stmt)
            conv = result.scalars().first()
            assert conv is not None

            stmt = select(ConversationMessage).where(ConversationMessage.conversation_id == conv.id)
            result = await db.execute(stmt)
            messages = result.scalars().all()

            assert any(m.role == "assistant" and "Parijs" in m.content for m in messages)
            print(f"WhatsApp E2E Success: Assistant replied '{messages[-1].content}'")
