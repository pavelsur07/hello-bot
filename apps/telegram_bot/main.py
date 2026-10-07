"""Run the first Telegram-to-Markdown flow in demo or polling mode."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))

from hello_bot.channels.telegram.adapter import TelegramAdapter, TelegramApiError, TelegramClient, parse_update
from hello_bot.conversations.answer_from_knowledge import answer, process_update
from hello_bot.knowledge.markdown import MarkdownKnowledge
from hello_bot.storage.sqlite_events import SQLiteEventStore


async def process_batch(updates, sender, events, knowledge, offset: int | None) -> int | None:
    """Process in update-id order, stopping before acknowledging a failed send."""
    for payload in sorted(updates, key=lambda item: json.loads(item)["update_id"]):
        update_id = json.loads(payload)["update_id"]
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
            print("У бота установлен webhook. Проверьте getWebhookInfo и удалите webhook вручную перед polling.", file=sys.stderr)
            return 2
    except TelegramApiError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    sender = TelegramAdapter(client)
    events = SQLiteEventStore(db_path)
    offset = None
    try:
        await events.recover_pending()
        while True:
            try:
                updates = await client.get_updates(offset)
                previous = offset
                offset = await process_batch(updates, sender, events, knowledge, offset)
                if updates and offset == previous:
                    await asyncio.sleep(2)
            except (TelegramApiError, OSError, ValueError) as exc:
                print(f"Ошибка polling: {exc}", file=sys.stderr)
                await asyncio.sleep(2)
    finally:
        events.close()


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Telegram-to-Markdown bot")
    parser.add_argument("--demo-update", type=Path, help="Локальный update JSON без сети и токена")
    parser.add_argument("--knowledge-dir", type=Path, default=Path("knowledge"))
    parser.add_argument("--db-path", type=Path, default=Path(".local/events.sqlite3"))
    args = parser.parse_args(argv)
    knowledge = MarkdownKnowledge(_repository_path(args.knowledge_dir))
    if args.demo_update:
        return await run_demo(_repository_path(args.demo_update), knowledge)
    return await run_polling(knowledge, _repository_path(args.db_path))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
