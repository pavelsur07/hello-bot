"""Minimum persistence boundary for processing incoming events once."""

from typing import Protocol

from hello_bot.core import Channel


class EventStore(Protocol):
    async def claim(self, channel: Channel, external_event_id: str) -> bool:
        """Atomically claim an event; return False if it was already claimed."""
        ...

    async def mark_sent(self, channel: Channel, external_event_id: str) -> None: ...

    async def release(self, channel: Channel, external_event_id: str) -> None: ...

    async def recover_pending(self) -> None: ...
