"""SMTP transport for dynamic guest and laundry recipients."""
from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
import smtplib
import ssl

from homeassistant.core import HomeAssistant


class MailError(Exception):
    """Raised when SMTP is not configured or sending fails."""


@dataclass(slots=True)
class MailSettings:
    host: str
    port: int
    username: str
    password: str
    sender: str
    starttls: bool = True
    use_ssl: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.host and self.port and self.sender)


class MailTransport:
    def __init__(self, hass: HomeAssistant, settings: MailSettings) -> None:
        self._hass = hass
        self.settings = settings

    async def async_send(self, to: str, subject: str, body: str) -> None:
        if not self.settings.configured:
            raise MailError("SMTP ist nicht vollständig konfiguriert")
        recipient = str(to or "").strip()
        if not recipient:
            raise MailError("E-Mail-Empfänger fehlt")
        await self._hass.async_add_executor_job(self._send_sync, recipient, subject, body)

    def _send_sync(self, recipient: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.settings.sender
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content(body)

        try:
            if self.settings.use_ssl:
                with smtplib.SMTP_SSL(
                    self.settings.host,
                    self.settings.port,
                    timeout=30,
                    context=ssl.create_default_context(),
                ) as smtp:
                    if self.settings.username:
                        smtp.login(self.settings.username, self.settings.password)
                    smtp.send_message(msg)
                return

            with smtplib.SMTP(self.settings.host, self.settings.port, timeout=30) as smtp:
                smtp.ehlo()
                if self.settings.starttls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                if self.settings.username:
                    smtp.login(self.settings.username, self.settings.password)
                smtp.send_message(msg)
        except Exception as err:
            raise MailError(str(err)) from err
