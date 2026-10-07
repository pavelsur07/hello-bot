"""Operations a channel adapter must provide."""

from typing import Protocol

from hello_bot.core import InboundMessage, OutboundMessage


class DeliveryUncertainError(RuntimeError):
    """The external service may have accepted a reply; retry is not safe."""


class ChannelAdapter(Protocol):
    def parse_event(self, payload: bytes) -> InboundMessage | None: ...

    async def send(self, message: InboundMessage, response: OutboundMessage) -> None:
        """Raise DeliveryUncertainError if a failed request may have delivered the reply."""
        ...
