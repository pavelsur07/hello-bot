"""Run the first Telegram-to-Markdown flow in demo or polling mode."""

import argparse
import asyncio
import io
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path

from hello_bot.channels.contracts import ChannelAdapter
from hello_bot.channels.telegram.adapter import (
    TelegramAdapter,
    TelegramApiError,
    TelegramClient,
    parse_update,
)
from hello_bot.conversations.answer_from_knowledge import DeliveryStateError, answer, process_update
from hello_bot.knowledge.contracts import KnowledgeSearch
from hello_bot.knowledge.markdown import MarkdownKnowledge
from hello_bot.storage.contracts import EventStore
from hello_bot.storage.sqlite_events import SQLiteEventStore

ROOT = Path(__file__).resolve().parents[2]


def _update_id(payload: bytes) -> int:
    update = json.loads(payload)
    if not isinstance(update, dict):
        raise ValueError("Telegram update должен быть объектом")
    event_id = update.get("update_id")
    if type(event_id) is not int or event_id < 0:
        raise ValueError("Некорректный update_id")
    return event_id


async def process_batch(
    updates: Iterable[bytes],
    sender: ChannelAdapter,
    events: EventStore,
    knowledge: KnowledgeSearch,
    offset: int | None,
) -> int | None:
    """Process in update-id order, stopping before acknowledging a failed send."""
    for payload in sorted(updates, key=_update_id):
        update_id = _update_id(payload)
        if not await process_update(payload, sender, events, knowledge):
            break
        offset = update_id + 1
    return offset


def _repository_path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


async def run_demo(update_path: Path, knowledge: MarkdownKnowledge) -> int:
    message = parse_update(update_path.read_bytes())
    if message is None:
        print("Демо-событие не содержит личного текстового сообщения", file=sys.stderr)
        return 2
    response = await answer(message, knowledge)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    print(response.text)
    return 0


async def run_polling(knowledge: MarkdownKnowledge, db_path: Path) -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Укажите TELEGRAM_BOT_TOKEN в окружении", file=sys.stderr)
        return 2
    client = TelegramClient(token)
    try:
        if await client.get_webhook_url():
            print(
                "У бота установлен webhook. Проверьте getWebhookInfo и удалите webhook вручную перед polling.",
                file=sys.stderr,
            )
            return 2
    except TelegramApiError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    sender = TelegramAdapter(client)
    events = SQLiteEventStore(db_path)
    offset = None
    try:
        if await events.has_pending():
            print(
                "Есть pending-события с неизвестным исходом. Проверьте доставку и согласуйте восстановление перед запуском.",
                file=sys.stderr,
            )
            return 2
        while True:
            try:
                updates = await client.get_updates(offset)
                previous = offset
                offset = await process_batch(updates, sender, events, knowledge, offset)
                if updates and offset == previous:
                    await asyncio.sleep(2)
            except (TelegramApiError, OSError, ValueError) as exc:
                print(
                    f"Ошибка polling ({type(exc).__name__}); повтор получения событий",
                    file=sys.stderr,
                )
                await asyncio.sleep(2)
    finally:
        events.close()


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Telegram-to-Markdown bot")
    parser.add_argument("--demo-update", type=Path, help="Локальный update JSON без сети и токена")
    parser.add_argument("--knowledge-dir", type=Path, default=Path("knowledge"))
    parser.add_argument("--db-path", type=Path, default=Path(".local/events.sqlite3"))
    args = parser.parse_args(argv)
    try:
        knowledge = MarkdownKnowledge(_repository_path(args.knowledge_dir), repository_root=ROOT)
        if args.demo_update:
            return await run_demo(_repository_path(args.demo_update), knowledge)
        return await run_polling(knowledge, _repository_path(args.db_path))
    except DeliveryStateError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print(
            "Ошибка конфигурации или данных; проверьте пути, Markdown и формат события",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
