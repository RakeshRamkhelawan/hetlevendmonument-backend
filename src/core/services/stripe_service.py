import asyncio
from typing import Any, Optional, cast

import stripe
from loguru import logger
from stripe.error import SignatureVerificationError, StripeError

from src.core.config.unified_config import config


class StripeNotConfiguredError(RuntimeError):
    """Stripe API key is not configured; the requested operation cannot run.

    Raised instead of silently degrading to mock behaviour (BE-SEC-058).
    """


class StripeWebhookSecretMissingError(RuntimeError):
    """Webhook signing secret is not configured; refuse to parse the payload.

    Fail-closed (BE-SEC-058): without the endpoint secret Stripe's official
    guidance is to never trust or parse the event body.
    """


class StripeService:
    """
    Service for handling Stripe payments, subscriptions, and customers.
    Integrated with the Sanskriti Setu Unified Backend.
    All synchronous Stripe SDK calls are executed in a thread pool to avoid
    blocking the async event loop.
    """

    def __init__(self) -> None:
        self.api_key = config.stripe_api_key
        if self.api_key:
            logger.info("Stripe Service initialized successfully.")
        else:
            logger.warning(
                "Stripe API key not found in configuration. "
                "Stripe Service features will be limited."
            )

    async def create_customer(
        self,
        email: str,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str | None:
        """Create a new customer in Stripe. Returns the Stripe Customer ID."""
        if not self.api_key:
            logger.error("Cannot create customer: Stripe API key missing.")
            return None

        try:
            customer = await asyncio.to_thread(
                stripe.Customer.create,
                email=email,
                name=name,
                metadata=metadata or {},
                api_key=self.api_key,
            )
            logger.info("Created Stripe customer: %s for %s", customer.id, email)
            return cast(str, customer.id)
        except StripeError as e:
            logger.error(
                "Stripe error creating customer: %s: %s",
                type(e).__name__,
                e.user_message or str(e),
            )
            return None
        except Exception as e:
            logger.error(
                "Unexpected error creating customer: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            return None

    async def create_checkout_session(
        self,
        customer_id: str,
        success_url: str,
        cancel_url: str,
        price_id: str,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str | None:
        """Create a Stripe Checkout Session for a subscription.

        Returns the session URL for redirection.
        """
        if not self.api_key:
            return None

        try:
            session = await asyncio.to_thread(
                stripe.checkout.Session.create,
                customer=customer_id,
                payment_method_types=["card"],
                line_items=[
                    {
                        "price": price_id,
                        "quantity": 1,
                    }
                ],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata or {},
                api_key=self.api_key,
            )
            return cast(Optional[str], session.url)
        except Exception as e:
            logger.error(
                "Error creating checkout session: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            return None

    async def create_donation_checkout_session(
        self,
        amount_cents: int,
        currency: str = "eur",
        donor_email: str | None = None,
        is_monthly: bool = False,
        success_url: str = "",
        cancel_url: str = "",
        metadata: dict[str, str] | None = None,
    ) -> tuple[str | None, str | None]:
        """Create a Stripe Checkout Session for a donation or adoption.

        Supports one-time payments (mode=payment) and monthly recurring support (mode=subscription).
        Returns a tuple of (checkout_url, session_id).

        Raises:
            StripeNotConfiguredError: when no Stripe API key is configured.
                Fail-closed (BE-SEC-058): no mock checkout session is generated,
                so no fake donation can ever reach the transparency statistics.
        """
        if not self.api_key:
            raise StripeNotConfiguredError(
                "Stripe API key is not configured; donation checkout unavailable."
            )

        try:
            line_item_price_data: dict[str, object] = {
                "currency": currency,
                "product_data": {
                    "name": "Donatie Levend Monument",
                    "description": "Bijdrage aan erfgoedbehoud en gemeenschapsverhalen",
                },
                "unit_amount": amount_cents,
            }
            if is_monthly:
                line_item_price_data["recurring"] = {"interval": "month"}

            mode = "subscription" if is_monthly else "payment"

            session = await asyncio.to_thread(
                stripe.checkout.Session.create,
                customer_email=donor_email,
                payment_method_types=["card", "ideal"],
                line_items=[
                    {
                        "price_data": line_item_price_data,
                        "quantity": 1,
                    }
                ],
                mode=mode,
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata or {},
                api_key=self.api_key,
            )
            return cast(Optional[str], session.url), cast(Optional[str], session.id)
        except Exception as e:
            logger.error(
                "Error creating donation checkout session: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            return None, None

    def construct_webhook_event(
        self,
        payload: bytes,
        sig_header: str | None,
        webhook_secret: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Construct and verify a Stripe Webhook event from raw bytes and signature header.

        Fail-closed (BE-SEC-058), per Stripe's official guidance
        (https://docs.stripe.com/webhooks/signature):
        - No webhook signing secret configured -> StripeWebhookSecretMissingError;
          the payload is NEVER parsed without verification.
        - Missing Stripe-Signature header -> ValueError.
        - Invalid signature -> ValueError (wraps stripe SignatureVerificationError).

        Signature verification only requires the endpoint secret; the Stripe API
        key plays no role here and is therefore not consulted.
        """
        secret = webhook_secret or getattr(config, "stripe_webhook_secret", None)
        if not secret or not secret.strip():
            logger.error(
                "Stripe webhook received but no webhook signing secret is configured; "
                "refusing to parse the payload (fail-closed)."
            )
            raise StripeWebhookSecretMissingError(
                "Stripe webhook signing secret is not configured."
            )

        if not sig_header:
            raise ValueError("Missing stripe-signature header")

        try:
            return cast(
                dict[str, Any],  # TODO(TYPE): replace Any with concrete type
                stripe.Webhook.construct_event(payload, sig_header, secret),
            )
        except SignatureVerificationError as exc:
            logger.warning("Stripe webhook signature verification failed.")
            raise ValueError("Invalid Stripe webhook signature") from exc
        except Exception as exc:
            logger.error(
                "Stripe webhook event construction failed: %s",
                type(exc).__name__,
            )
            raise


# Global instance (lazy initialization is handled by the class itself)
stripe_service = StripeService()
