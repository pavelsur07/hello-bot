"""Channel-independent answer flow for the first Markdown knowledge slice."""

from hello_bot.channels.contracts import ChannelAdapter, DeliveryUncertainError
from hello_bot.core import InboundMessage, OutboundMessage
from hello_bot.knowledge.contracts import KnowledgeSearch
from hello_bot.storage.contracts import EventStore

FALLBACK = (
    "Не нашёл подтверждённого ответа в базе знаний. Уточните вопрос или обратитесь к оператору."
)
LONG_SECTION_FALLBACK = (
    "Найденный раздел слишком длинный для автоматического ответа. Обратитесь к оператору."
)
MAX_AUTOMATIC_RESPONSE_LENGTH = 3500


class DeliveryStateError(RuntimeError):
    """Delivery or its persisted state is uncertain; processing must stop."""


async def answer(message: InboundMessage, knowledge: KnowledgeSearch) -> OutboundMessage:
    hits = await knowledge.search(message.text, limit=1)
    if not hits:
        return OutboundMessage(FALLBACK)
    hit = hits[0]
    source = f"Источник: {hit.title} — {hit.section_title}"
    response_text = f"{hit.text}\n\n{source}"
    if len(response_text) > MAX_AUTOMATIC_RESPONSE_LENGTH:
        response_text = f"{LONG_SECTION_FALLBACK}\n\n{source}"
    if len(response_text) > MAX_AUTOMATIC_RESPONSE_LENGTH:
        response_text = (
            f"{LONG_SECTION_FALLBACK}\n\nИсточник: {hit.source_path}::{hit.section_title}"
        )
    if len(response_text) > MAX_AUTOMATIC_RESPONSE_LENGTH:
        response_text = LONG_SECTION_FALLBACK
    return OutboundMessage(
        text=response_text,
        source_refs=(f"{hit.source_path}::{hit.section_title}",),
    )


async def process_update(
    payload: bytes,
    sender: ChannelAdapter,
    events: EventStore,
    knowledge: KnowledgeSearch,
) -> bool:
    message = sender.parse_event(payload)
    if message is None:
        return True
    if not await events.claim(message.channel, message.external_event_id):
        return True
    try:
        response = await answer(message, knowledge)
        await sender.send(message, response)
    except DeliveryUncertainError:
        raise DeliveryStateError(
            "Неизвестен исход отправки; остановите polling и проверьте доставку"
        ) from None
    except Exception:
        await events.release(message.channel, message.external_event_id)
        return False
    try:
        await events.mark_sent(message.channel, message.external_event_id)
    except Exception as exc:
        raise DeliveryStateError(
            "Ответ отправлен, но статус доставки не сохранён; остановите polling"
        ) from exc
    return True
