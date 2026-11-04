"""
Mocked External API Integration Tests

This module provides tests for external API integrations (Stripe, SendGrid, etc.)
using mocks instead of making real API calls. This allows tests to run in CI/CD
without requiring actual API keys or incurring costs.

Tests cover:
- Stripe payments and checkout sessions
- Email service (SendGrid/AWS SES)
- File storage (AWS S3)
- SMS/Twilio
- External webhooks

All tests use mocked services to ensure deterministic, fast, and isolated execution.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ============================================================================
# STRIPE API TESTS (Mocked)
# ============================================================================


@pytest.mark.asyncio
class TestStripeAPIMocked:
    """Test Stripe API integration with mocked responses."""

    async def test_create_customer_with_mock(self, mock_stripe_service):
        """Test customer creation with mocked Stripe service."""
        customer_id = await mock_stripe_service.create_customer(
            email="customer@example.com",
            name="Test Customer",
            metadata={"tenant_id": "123", "source": "test"},
        )

        assert customer_id is not None
        assert customer_id.startswith("cus_mock_")

        # Verify customer is stored
        customer = await mock_stripe_service.retrieve_customer(customer_id)
        assert customer.email == "customer@example.com"
        assert customer.name == "Test Customer"

    async def test_create_checkout_session_with_mock(self, mock_stripe_service):
        """Test checkout session creation with mocked Stripe."""
        # Create customer first
        customer_id = await mock_stripe_service.create_customer(email="customer@example.com")

        # Create checkout session
        session_url = await mock_stripe_service.create_checkout_session(
            customer_id=customer_id,
            success_url="https://example.com/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://example.com/cancel",
            price_id="price_1234567890",
        )

        assert session_url is not None
        assert "checkout.stripe.com" in session_url
        assert "cs_mock_" in session_url

    async def test_checkout_session_retrieval(self, mock_stripe_service):
        """Test retrieving a checkout session."""
        customer_id = await mock_stripe_service.create_customer(email="customer@example.com")

        session_url = await mock_stripe_service.create_checkout_session(
            customer_id=customer_id,
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            price_id="price_test",
        )

        # Extract session ID and retrieve
        session_id = session_url.split("/")[-1]
        session = await mock_stripe_service.retrieve_session(session_id)

        assert session is not None
        assert session.id == session_id
        assert session.customer == customer_id
        assert session.payment_status == "unpaid"

    async def test_stripe_error_handling(self, mock_stripe_service):
        """Test error handling when Stripe API fails."""
        mock_stripe_service.set_fail_mode(True)

        customer_id = await mock_stripe_service.create_customer(email="customer@example.com")

        assert customer_id is None

    async def test_multiple_customers(self, mock_stripe_service):
        """Test creating multiple customers with unique IDs."""
        emails = [f"user{i}@example.com" for i in range(5)]
        customer_ids = []

        for email in emails:
            customer_id = await mock_stripe_service.create_customer(email=email)
            customer_ids.append(customer_id)

        # All IDs should be unique
        assert len(set(customer_ids)) == 5
        assert all(cid.startswith("cus_mock_") for cid in customer_ids)

    async def test_customer_metadata_storage(self, mock_stripe_service):
        """Test that customer metadata is properly stored."""
        metadata = {
            "tenant_id": "456",
            "plan": "enterprise",
            "signup_source": "api",
        }

        customer_id = await mock_stripe_service.create_customer(
            email="enterprise@example.com",
            name="Enterprise Customer",
            metadata=metadata,
        )

        customer = await mock_stripe_service.retrieve_customer(customer_id)
        assert customer.metadata == metadata


# ============================================================================
# EMAIL SERVICE TESTS (Mocked)
# ============================================================================


@pytest.mark.asyncio
class TestEmailServiceMocked:
    """Test email service integration with mocked providers."""

    async def test_send_simple_email(self, mock_email_service):
        """Test sending a simple plain text email."""
        result = await mock_email_service.send(
            to="recipient@example.com",
            subject="Test Subject",
            body="This is a test email body.",
        )

        assert result is True
        assert len(mock_email_service.sent_emails) == 1

        email = mock_email_service.sent_emails[0]
        assert email.to == "recipient@example.com"
        assert email.subject == "Test Subject"
        assert email.body == "This is a test email body."
        assert email.sent_at is not None

    async def test_send_html_email(self, mock_email_service):
        """Test sending an HTML email."""
        html_content = "<html><body><h1>Welcome</h1><p>Thank you for signing up!</p></body></html>"

        result = await mock_email_service.send(
            to="user@example.com",
            subject="Welcome to Our Service",
            body="Plain text fallback",
            html_body=html_content,
        )

        assert result is True
        email = mock_email_service.sent_emails[0]
        assert email.html_body == html_content

    async def test_send_template_email(self, mock_email_service):
        """Test sending a template-based email."""
        context = {
            "user_name": "John Doe",
            "company_name": "Acme Inc",
            "activation_url": "https://example.com/activate?token=abc123",
        }

        result = await mock_email_service.send_template(
            to="john@example.com",
            template_name="account_activation",
            context=context,
        )

        assert result is True
        assert len(mock_email_service.sent_emails) == 1

        # Verify call was logged with correct template
        assert mock_email_service.call_log[0]["template_name"] == "account_activation"
        assert mock_email_service.call_log[0]["context"] == context

    async def test_email_failure_handling(self, mock_email_service):
        """Test handling of email service failures."""
        mock_email_service.set_fail_mode(True)

        result = await mock_email_service.send(
            to="recipient@example.com",
            subject="Test",
            body="Body",
        )

        assert result is False
        assert len(mock_email_service.sent_emails) == 0

    async def test_multiple_recipients(self, mock_email_service):
        """Test sending emails to multiple recipients."""
        recipients = ["user1@example.com", "user2@example.com", "user3@example.com"]

        for recipient in recipients:
            await mock_email_service.send(
                to=recipient,
                subject="Broadcast",
                body="This is a broadcast message.",
            )

        assert len(mock_email_service.sent_emails) == 3

        # Verify each recipient received the email
        sent_recipients = [e.to for e in mock_email_service.sent_emails]
        assert set(sent_recipients) == set(recipients)

    async def test_email_filtering(self, mock_email_service):
        """Test filtering sent emails by recipient."""
        # Send emails to different recipients
        await mock_email_service.send(to="alice@example.com", subject="A1", body="Body 1")
        await mock_email_service.send(to="bob@example.com", subject="B1", body="Body 2")
        await mock_email_service.send(to="alice@example.com", subject="A2", body="Body 3")

        # Filter for Alice
        alice_emails = mock_email_service.get_sent_emails(to="alice@example.com")
        assert len(alice_emails) == 2
        assert all(e.to == "alice@example.com" for e in alice_emails)


# ============================================================================
# FILE STORAGE TESTS (Mocked S3)
# ============================================================================


class MockS3Client:
    """Mock AWS S3 client for testing."""

    def __init__(self):
        self._buckets: dict = {}
        self._objects: dict = {}  # bucket -> {key: data}
        self.call_log: list = []

    async def create_bucket(self, bucket_name: str) -> bool:
        """Mock create bucket."""
        self.call_log.append({"method": "create_bucket", "bucket": bucket_name})
        self._buckets[bucket_name] = {"created": datetime.now(timezone.utc)}
        self._objects[bucket_name] = {}
        return True

    async def put_object(self, bucket: str, key: str, data: bytes) -> bool:
        """Mock upload object."""
        self.call_log.append({"method": "put_object", "bucket": bucket, "key": key})
        if bucket not in self._objects:
            self._objects[bucket] = {}
        self._objects[bucket][key] = data
        return True

    async def get_object(self, bucket: str, key: str) -> bytes:
        """Mock download object."""
        self.call_log.append({"method": "get_object", "bucket": bucket, "key": key})
        if bucket in self._objects and key in self._objects[bucket]:
            return self._objects[bucket][key]
        raise Exception("Object not found")

    async def delete_object(self, bucket: str, key: str) -> bool:
        """Mock delete object."""
        self.call_log.append({"method": "delete_object", "bucket": bucket, "key": key})
        if bucket in self._objects and key in self._objects[bucket]:
            del self._objects[bucket][key]
            return True
        return False

    async def list_objects(self, bucket: str, prefix: str = "") -> list:
        """Mock list objects."""
        self.call_log.append({"method": "list_objects", "bucket": bucket, "prefix": prefix})
        if bucket not in self._objects:
            return []
        keys = [k for k in self._objects[bucket].keys() if k.startswith(prefix)]
        return [{"Key": k} for k in keys]


@pytest.fixture
def mock_s3_client():
    """Provide MockS3Client for testing."""
    return MockS3Client()


@pytest.mark.asyncio
class TestS3StorageMocked:
    """Test S3 storage integration with mocked client."""

    async def test_create_bucket(self, mock_s3_client):
        """Test creating an S3 bucket."""
        result = await mock_s3_client.create_bucket("test-bucket")

        assert result is True
        assert "test-bucket" in mock_s3_client._buckets

    async def test_upload_object(self, mock_s3_client):
        """Test uploading an object to S3."""
        await mock_s3_client.create_bucket("test-bucket")

        data = b"Hello, World!"
        result = await mock_s3_client.put_object(
            bucket="test-bucket",
            key="uploads/test.txt",
            data=data,
        )

        assert result is True
        assert "uploads/test.txt" in mock_s3_client._objects["test-bucket"]

    async def test_download_object(self, mock_s3_client):
        """Test downloading an object from S3."""
        await mock_s3_client.create_bucket("test-bucket")

        original_data = b"Test file content"
        await mock_s3_client.put_object("test-bucket", "test.txt", original_data)

        downloaded = await mock_s3_client.get_object("test-bucket", "test.txt")
        assert downloaded == original_data

    async def test_delete_object(self, mock_s3_client):
        """Test deleting an object from S3."""
        await mock_s3_client.create_bucket("test-bucket")
        await mock_s3_client.put_object("test-bucket", "delete_me.txt", b"data")

        result = await mock_s3_client.delete_object("test-bucket", "delete_me.txt")

        assert result is True
        assert "delete_me.txt" not in mock_s3_client._objects["test-bucket"]

    async def test_list_objects_with_prefix(self, mock_s3_client):
        """Test listing objects with a prefix filter."""
        await mock_s3_client.create_bucket("test-bucket")

        # Add multiple objects
        await mock_s3_client.put_object("test-bucket", "docs/readme.txt", b"readme")
        await mock_s3_client.put_object("test-bucket", "docs/guide.md", b"guide")
        await mock_s3_client.put_object("test-bucket", "images/logo.png", b"logo")

        # List only docs
        docs = await mock_s3_client.list_objects("test-bucket", prefix="docs/")
        assert len(docs) == 2

        keys = [d["Key"] for d in docs]
        assert "docs/readme.txt" in keys
        assert "docs/guide.md" in keys


# ============================================================================
# WEBHOOK TESTS (Mocked)
# ============================================================================


@pytest.mark.asyncio
class TestWebhookHandlingMocked:
    """Test webhook handling with mocked external services."""

    async def test_stripe_webhook_signature_verification(self):
        """Test Stripe webhook signature verification."""

        # Mock the webhook handler
        async def handle_stripe_webhook(payload: dict, signature: str) -> bool:
            """Mock webhook handler that verifies signature."""
            expected_signature = "mock_signature_valid"
            return signature == expected_signature

        # Test with valid signature
        result = await handle_stripe_webhook(
            {"type": "checkout.session.completed"},
            "mock_signature_valid",
        )
        assert result is True

        # Test with invalid signature
        result = await handle_stripe_webhook(
            {"type": "checkout.session.completed"},
            "invalid_signature",
        )
        assert result is False

    async def test_stripe_webhook_event_processing(self):
        """Test processing of Stripe webhook events."""
        events_processed = []

        async def process_stripe_event(event_type: str, data: dict):
            """Mock event processor."""
            events_processed.append({"type": event_type, "data": data})

        # Simulate various webhook events
        test_events = [
            ("checkout.session.completed", {"session_id": "cs_123"}),
            ("invoice.paid", {"invoice_id": "inv_456"}),
            ("customer.subscription.created", {"subscription_id": "sub_789"}),
        ]

        for event_type, data in test_events:
            await process_stripe_event(event_type, data)

        assert len(events_processed) == 3
        assert events_processed[0]["type"] == "checkout.session.completed"
        assert events_processed[1]["type"] == "invoice.paid"


# ============================================================================
# SMS/TWILIO TESTS (Mocked)
# ============================================================================


class MockTwilioClient:
    """Mock Twilio client for testing SMS."""

    def __init__(self):
        self.messages = MockTwilioMessages()
        self.call_log: list = []


class MockTwilioMessages:
    """Mock Twilio messages resource."""

    def __init__(self):
        self.sent: list = []

    async def create_async(self, to: str, from_: str, body: str) -> MagicMock:
        """Mock sending an SMS."""
        message = MagicMock()
        message.sid = f"SM{datetime.now(timezone.utc).timestamp()}"
        message.to = to
        message.from_ = from_
        message.body = body
        message.status = "queued"

        self.sent.append(
            {
                "sid": message.sid,
                "to": to,
                "from": from_,
                "body": body,
            }
        )

        return message


@pytest.fixture
def mock_twilio_client():
    """Provide MockTwilioClient for testing."""
    return MockTwilioClient()


@pytest.mark.asyncio
class TestTwilioSMSMocked:
    """Test Twilio SMS integration with mocked client."""

    async def test_send_sms(self, mock_twilio_client):
        """Test sending an SMS message."""
        message = await mock_twilio_client.messages.create_async(
            to="+1234567890",
            from_="+0987654321",
            body="Hello from test!",
        )

        assert message is not None
        assert message.sid is not None
        assert message.to == "+1234567890"
        assert message.body == "Hello from test!"

        # Verify message was recorded
        assert len(mock_twilio_client.messages.sent) == 1
        assert mock_twilio_client.messages.sent[0]["to"] == "+1234567890"

    async def test_send_multiple_sms(self, mock_twilio_client):
        """Test sending multiple SMS messages."""
        recipients = ["+1111111111", "+2222222222", "+3333333333"]

        for recipient in recipients:
            await mock_twilio_client.messages.create_async(
                to=recipient,
                from_="+0987654321",
                body="Broadcast message",
            )

        assert len(mock_twilio_client.messages.sent) == 3
        sent_recipients = [m["to"] for m in mock_twilio_client.messages.sent]
        assert set(sent_recipients) == set(recipients)


# ============================================================================
# INTEGRATION TESTS WITH PATCHED SERVICES
# ============================================================================


@pytest.mark.asyncio
class TestServiceIntegrationWithMocks:
    """Test integration of services with mocked external APIs."""

    async def test_payment_flow_with_email_notification(
        self, mock_stripe_service, mock_email_service
    ):
        """
        Test complete payment flow:
        1. Create Stripe customer
        2. Create checkout session
        3. Send confirmation email
        """
        # Step 1: Create customer
        customer_email = "customer@example.com"
        customer_id = await mock_stripe_service.create_customer(
            email=customer_email,
            name="Test Customer",
        )
        assert customer_id is not None

        # Step 2: Create checkout session
        session_url = await mock_stripe_service.create_checkout_session(
            customer_id=customer_id,
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            price_id="price_premium",
        )
        assert session_url is not None

        # Step 3: Send confirmation email
        email_result = await mock_email_service.send_template(
            to=customer_email,
            template_name="payment_initiated",
            context={
                "customer_name": "Test Customer",
                "checkout_url": session_url,
            },
        )
        assert email_result is True

        # Verify all interactions
        assert len(mock_stripe_service.call_log) == 2  # create_customer + create_checkout_session
        assert len(mock_email_service.sent_emails) == 1

    async def test_file_upload_notification_flow(self, mock_s3_client, mock_email_service):
        """
        Test file upload with email notification:
        1. Upload file to S3
        2. Send notification email with file URL
        """
        # Step 1: Upload file
        await mock_s3_client.create_bucket("user-uploads")
        file_data = b"PDF file content here"
        await mock_s3_client.put_object(
            bucket="user-uploads",
            key="documents/report.pdf",
            data=file_data,
        )

        # Step 2: Send notification
        file_url = "https://s3.amazonaws.com/user-uploads/documents/report.pdf"
        email_result = await mock_email_service.send(
            to="user@example.com",
            subject="Your file has been uploaded",
            body=f"Your file is available at: {file_url}",
        )

        assert email_result is True
        assert len(mock_s3_client.call_log) == 2  # create_bucket + put_object
        assert len(mock_email_service.sent_emails) == 1
        assert "report.pdf" in mock_email_service.sent_emails[0].body
