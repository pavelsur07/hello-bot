"""Operations a channel adapter must provide."""

from typing import Protocol

from hello_bot.core import InboundMessage, OutboundMessage


class ChannelAdapter(Protocol):
    def parse_event(self, payload: bytes) -> InboundMessage | None: ...

    async def send(self, message: InboundMessage, response: OutboundMessage) -> None: ...
