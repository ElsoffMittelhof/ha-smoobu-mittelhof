"""Runtime container."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .api import SmoobuApiClient
from .coordinator import SmoobuCoordinator
from .laundry import LaundryRepository
from .mail import MailTransport
from .storage import SmoobuStateStore
from .templates import TemplateRepository


@dataclass(slots=True)
class SmoobuRuntime:
    api: SmoobuApiClient
    coordinator: SmoobuCoordinator
    store: SmoobuStateStore
    templates: TemplateRepository
    laundry: LaundryRepository
    mail: MailTransport
    config_directory: Path
    houses: dict[int, str]
    workflow: Any = None
    guest_drafts: Any = None
    guest_inbox: Any = None
    accounting: Any = None
    guest_unsub: Any = None
    guest_timer_unsub: Any = None
    guest_message_send_enabled: bool = False
    guest_portal_enabled: bool = False
