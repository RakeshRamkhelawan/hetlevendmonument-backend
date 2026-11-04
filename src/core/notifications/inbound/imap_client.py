"""IMAP client for inbound email processing.

Supports:
- IDLE mode (push notifications)
- Polling fallback
- Multi-tenant mailbox support
- Auto-reconnect
"""

import asyncio
import email
import imaplib
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from typing import Any, List, Optional, Union, cast
from collections.abc import AsyncIterator, Awaitable, Callable

from loguru import logger


@dataclass
class IMAPConfig:
    """Configuration for IMAP connection."""

    host: str
    port: int = 993
    username: str = ""
    password: str = ""
    use_ssl: bool = True
    mailbox: str = "INBOX"
    poll_interval: int = 60  # seconds (fallback)
    idle_timeout: int = 29 * 60  # 29 minutes (IMAP IDLE max)


@dataclass
class InboundEmail:
    """Parsed inbound email."""

    message_id: str
    thread_id: str
    from_address: str
    from_name: str
    to_addresses: list[str]
    cc_addresses: list[str]
    subject: str
    body_text: str
    body_html: str
    received_at: datetime
    raw_content: bytes
    headers: dict[str, str]


class IMAPClient:
    """Async IMAP client for inbound email processing.

    Features:
    - IDLE mode (push notifications)
    - Polling fallback
    - Auto-reconnect
    - Multi-tenant support via callback
    """

    def __init__(self, config: IMAPConfig) -> None:
        """Initialize IMAP client.

        Args:
            config: IMAP configuration
        """
        self.config = config
        self._connection: imaplib.IMAP4_SSL | imaplib.IMAP4 | None = None
        self._running = False
        self._reconnect_delay = 5  # seconds
        self._max_reconnect_delay = 300  # 5 minutes

    async def connect(self) -> bool:
        """Establish IMAP connection.

        Returns:
            True if connected successfully
        """
        try:
            # Create connection in thread pool (IMAP is blocking)
            loop = asyncio.get_event_loop()

            if self.config.use_ssl:
                self._connection = await loop.run_in_executor(
                    None, lambda: imaplib.IMAP4_SSL(self.config.host, self.config.port)
                )
            else:
                self._connection = await loop.run_in_executor(
                    None, lambda: imaplib.IMAP4(self.config.host, self.config.port)
                )

            # Login
            conn = self._connection
            assert conn is not None, "Connection should not be None after creation"
            _conn = conn
            await loop.run_in_executor(
                None,
                lambda: _conn.login(self.config.username, self.config.password),
            )

            # Select mailbox
            conn = self._connection
            assert conn is not None, "Connection should not be None after login"
            await loop.run_in_executor(None, lambda: conn.select(self.config.mailbox))

            logger.info(f"IMAP connected: {self.config.username}@{self.config.host}")
            return True

        except Exception as e:
            logger.error(f"IMAP connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Close IMAP connection."""
        if self._connection:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._connection.close)
                await loop.run_in_executor(None, self._connection.logout)
            except Exception as e:
                logger.warning(f"Error during IMAP disconnect: {e}")
            finally:
                self._connection = None

    async def listen(
        self,
        on_email: Callable[..., Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Listen for new emails.

        Uses IDLE if supported, falls back to polling.

        Args:
            on_email: Callback for new emails
        """
        self._running = True
        reconnect_delay = self._reconnect_delay

        while self._running:
            try:
                # Connect if not connected
                if not self._connection:
                    if not await self.connect():
                        logger.error(f"Reconnect failed, retrying in {reconnect_delay}s")
                        await asyncio.sleep(reconnect_delay)
                        reconnect_delay = min(reconnect_delay * 2, self._max_reconnect_delay)
                        continue
                    else:
                        reconnect_delay = self._reconnect_delay

                # Try IDLE mode first
                if await self._supports_idle():
                    logger.info("Using IMAP IDLE mode")
                    async for email_obj in self._idle_listen():
                        if not self._running:
                            break
                        await on_email(email_obj)
                else:
                    # Fallback to polling
                    logger.info("Using IMAP polling mode")
                    async for email_obj in self._poll_listen():
                        if not self._running:
                            break
                        await on_email(email_obj)

            except Exception as e:
                logger.error(f"IMAP listen error: {e}")
                await self.disconnect()
                await asyncio.sleep(reconnect_delay)

    def stop(self) -> None:
        """Stop listening."""
        self._running = False

    async def _supports_idle(self) -> bool:
        """Check if server supports IDLE mode."""
        if not self._connection:
            return False

        try:
            loop = asyncio.get_event_loop()

            # Check CAPABILITY
            conn = self._connection
            if conn is None:
                return False
            result = await loop.run_in_executor(None, lambda: conn.capability())

            capabilities = b" ".join(result[1]).decode().upper()
            return "IDLE" in capabilities

        except Exception as e:
            logger.warning(f"Could not check IDLE capability: {e}")
            return False

    async def _idle_listen(self) -> AsyncIterator[InboundEmail]:
        """IMAP IDLE mode (real-time push).

        Yields new emails as they arrive.
        """
        if not self._connection:
            return

        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # Send IDLE command
                if self._connection is None:
                    return
                tag = self._connection._new_tag().decode()
                self._connection.send(f"{tag} IDLE\r\n".encode())

                # Wait for notifications with timeout
                start_time = time.time()

                while self._running and time.time() - start_time < self.config.idle_timeout:
                    # Check for data with short timeout
                    conn = self._connection
                    if conn is None:
                        break
                    ready = await loop.run_in_executor(None, lambda: conn.socket().recv(1024))

                    if ready and b"EXISTS" in ready:
                        # New email arrived
                        logger.debug("New email notification via IDLE")

                        # Exit IDLE mode temporarily
                        conn2 = self._connection
                        if conn2 is None:
                            break
                        conn2.send(b"DONE\r\n")

                        # Fetch new emails
                        emails = await self._fetch_unseen()
                        for email_obj in emails:
                            yield email_obj

                        # Re-enter IDLE mode
                        conn3 = self._connection
                        if conn3 is None:
                            break
                        tag = conn3._new_tag().decode()
                        conn3.send(f"{tag} IDLE\r\n".encode())
                        start_time = time.time()  # Reset timeout

                    # Small delay to prevent busy loop
                    await asyncio.sleep(0.1)

                # Timeout reached, refresh IDLE
                conn4 = self._connection
                if conn4 is not None:
                    conn4.send(b"DONE\r\n")
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"IDLE mode error: {e}")
                await self.disconnect()
                raise

    async def _poll_listen(self) -> AsyncIterator[InboundEmail]:
        """Polling fallback (compatible with all servers).

        Yields new emails by polling at regular intervals.
        """
        while self._running:
            try:
                emails = await self._fetch_unseen()
                for email_obj in emails:
                    yield email_obj

                # Wait before next poll
                await asyncio.sleep(self.config.poll_interval)

            except Exception as e:
                logger.error(f"Polling error: {e}")
                await self.disconnect()
                raise

    async def _fetch_unseen(self) -> list[InboundEmail]:
        """Fetch all unseen emails.

        Returns: List[InboundEmail] of parsed inbound emails
        """
        if not self._connection:
            return []

        loop = asyncio.get_event_loop()
        emails: list[InboundEmail] = []
        try:
            # Search for unseen messages
            conn = self._connection
            if conn is None:
                return []
            result = await loop.run_in_executor(None, lambda: conn.search(None, "UNSEEN"))

            message_numbers = result[1][0].split() if result[1] and result[1][0] else []

            for msg_num in message_numbers:
                try:
                    # Fetch message
                    conn = self._connection
                    if conn is None:
                        continue
                    result = await loop.run_in_executor(
                        None, lambda: conn.fetch(msg_num, "(RFC822)")
                    )
                    if result is None or not result[1] or not result[1][0]:
                        continue
                    raw_email = result[1][0][1]

                    # Validate raw_email type
                    if not isinstance(raw_email, bytes):
                        logger.error(f"Unexpected raw_email type: {type(raw_email)}")
                        continue

                    # Parse email
                    email_obj = self._parse_email(raw_email)
                    emails.append(email_obj)

                    # Mark as seen
                    conn = self._connection
                    if conn is not None:
                        await loop.run_in_executor(
                            None, lambda: conn.store(msg_num, "+FLAGS", "\\Seen")
                        )

                    logger.info(f"Fetched email: {email_obj.message_id}")

                except Exception as e:
                    logger.error(f"Error parsing email {msg_num}: {e}")
                    continue

            return emails

        except Exception as e:
            logger.error(f"Error fetching unseen emails: {e}")
            return []

    def _parse_email(self, raw_email: bytes) -> InboundEmail:
        """Parse raw email bytes to InboundEmail.

        Args:
            raw_email: Raw email bytes

        Returns:
            Parsed InboundEmail
        """
        msg = email.message_from_bytes(raw_email)

        # Extract addresses
        from_addr = msg.get("From", "")
        from_email = self._extract_email(from_addr)
        from_name = self._extract_name(from_addr)

        to_addrs = self._parse_addresses(msg.get("To", ""))
        cc_addrs = self._parse_addresses(msg.get("Cc", ""))

        # Extract bodies
        body_text = self._extract_body(msg, "text/plain")
        body_html = self._extract_body(msg, "text/html")

        # Get message IDs
        message_id = msg.get("Message-ID", "")
        thread_id = msg.get("In-Reply-To") or message_id

        return InboundEmail(
            message_id=message_id,
            thread_id=thread_id,
            from_address=from_email,
            from_name=from_name,
            to_addresses=to_addrs,
            cc_addresses=cc_addrs,
            subject=msg.get("Subject", ""),
            body_text=body_text,
            body_html=body_html,
            received_at=datetime.now(timezone.utc),
            raw_content=raw_email,
            headers=dict(msg.items()),
        )

    def _extract_email(self, address: str) -> str:
        """Extract email from 'Name <email>' format."""
        import re

        match = re.search(r"<([^>]+)>", address)
        if match:
            return match.group(1)
        return address.strip()

    def _extract_name(self, address: str) -> str:
        """Extract name from 'Name <email>' format."""
        import re

        match = re.search(r"^([^<]+)", address)
        if match:
            return match.group(1).strip().strip('"')
        return ""

    def _parse_addresses(self, addresses: str) -> list[str]:
        """Parse comma-separated addresses."""
        if not addresses:
            return []
        return [self._extract_email(a.strip()) for a in addresses.split(",")]

    def _extract_body(self, msg: Message, content_type: str) -> str:
        """Extract body of specific content type."""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == content_type:
                    try:
                        return cast(bytes, part.get_payload(decode=True)).decode(
                            "utf-8", errors="replace"
                        )
                    except:
                        return ""
        else:
            if msg.get_content_type() == content_type:
                try:
                    return cast(bytes, msg.get_payload(decode=True)).decode(
                        "utf-8", errors="replace"
                    )
                except:
                    return ""
        return ""
