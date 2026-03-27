"""SMTP email sending with retry logic."""

from __future__ import annotations

import smtplib
import time
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Sequence


@dataclass
class EmailMessage:
    """Email message data."""

    to: Sequence[str]
    subject: str
    body: str
    cc: Sequence[str] | None = None
    bcc: Sequence[str] | None = None


class SMTPMailer:
    """SMTP mailer with retry logic."""

    def __init__(
        self,
        host: str,
        port: int,
        from_addr: str,
        username: str = "",
        password: str = "",
        use_tls: bool = True,
        max_retries: int = 3,
    ):
        """Initialize SMTP mailer.

        Args:
            host: SMTP server hostname
            port: SMTP server port
            from_addr: From email address
            username: SMTP authentication username
            password: SMTP authentication password
            use_tls: Use TLS for connection
            max_retries: Maximum retry attempts
        """
        self.host = host
        self.port = port
        self.from_addr = from_addr
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.max_retries = max_retries

    def send(self, message: EmailMessage) -> None:
        """Send an email with retry logic.

        Args:
            message: Email message to send

        Raises:
            Exception: If all retry attempts fail
        """
        mime_msg = self._build_mime_message(message)

        for attempt in range(self.max_retries + 1):
            try:
                self._send_smtp(mime_msg, message.to, message.cc, message.bcc)
                return
            except Exception as e:
                if attempt >= self.max_retries:
                    raise Exception(
                        f"Failed to send email after {self.max_retries} retries: {e}"
                    ) from e
                # Exponential backoff: 1s, 2s, 4s
                backoff = 2**attempt
                time.sleep(backoff)

    def _build_mime_message(self, message: EmailMessage) -> MIMEMultipart:
        """Build MIME message from email data."""
        msg = MIMEMultipart("alternative")
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(message.to)
        msg["Subject"] = message.subject

        if message.cc:
            msg["Cc"] = ", ".join(message.cc)
        if message.bcc:
            msg["Bcc"] = ", ".join(message.bcc)

        # Add text body
        text_part = MIMEText(message.body, "plain")
        msg.attach(text_part)

        return msg

    def _send_smtp(
        self,
        msg: MIMEMultipart,
        to: Sequence[str],
        cc: Sequence[str] | None,
        bcc: Sequence[str] | None,
    ) -> None:
        """Send email via SMTP."""
        # Build recipient list
        recipients = list(to)
        if cc:
            recipients.extend(cc)
        if bcc:
            recipients.extend(bcc)

        # Send via SMTP
        with smtplib.SMTP(self.host, self.port) as server:
            if self.use_tls:
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.send_message(msg, to_addrs=recipients)
