"""Internal message format shared by all channel adapters."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Channel(StrEnum):
    WEB = "web"
    TELEGRAM = "telegram"
    MAX = "max"


@dataclass(frozen=True, slots=True)
class InboundMessage:
    channel: Channel
    external_event_id: str
    external_user_id: str
    external_conversation_id: str
    text: str
    received_at: datetime


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    text: str
    source_refs: tuple[str, ...] = ()
