import json
import tempfile
import unittest
from pathlib import Path

from apps.telegram_bot.main import process_batch
from hello_bot.channels.telegram.adapter import parse_update
from hello_bot.knowledge.markdown import MarkdownKnowledge
from hello_bot.knowledge.models import KnowledgeHit
from hello_bot.storage.sqlite_events import SQLiteEventStore


ROOT = Path(__file__).resolve().parents[1]
CASES = {case["name"]: case["update"] for case in json.loads((ROOT / "tests" / "fixtures" / "telegram_updates.json").read_text(encoding="utf-8"))["cases"]}


def payload(name: str) -> bytes:
    return json.dumps(CASES[name], ensure_ascii=False).encode("utf-8")


class FakeSender:
    def __init__(self):
        self.sent = []
        self.fail_event = None

    def parse_event(self, update):
        return parse_update(update)

    async def send(self, message, response):
        if message.external_event_id == self.fail_event:
            raise RuntimeError("send failed")
        if len(response.text) > 4096:
            raise ValueError("Telegram text too long")
        self.sent.append(message.external_event_id)


class LongKnowledge:
    async def search(self, query, area=None, limit=5):
        return [KnowledgeHit("long-article", "examples/knowledge/long.md", "Длинный раздел", "Условие. " * 700, "Длинная статья", "support")]


class PollingBatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.store = SQLiteEventStore(Path(self.directory.name, "events.sqlite3"))
        self.knowledge = MarkdownKnowledge(ROOT / "examples" / "knowledge")
        self.sender = FakeSender()

    async def asyncTearDown(self):
        self.store.close()
        self.directory.cleanup()

    async def test_sorted_batch_stops_at_first_send_failure(self):
        self.sender.fail_event = "810002"
        updates = [payload("non_text_message"), payload("unknown_question"), payload("delivery_question")]
        offset = await process_batch(updates, self.sender, self.store, self.knowledge, None)
        self.assertEqual(offset, 810002)
        self.assertEqual(self.sender.sent, ["810001"])

    async def test_non_text_event_advances_offset(self):
        offset = await process_batch([payload("non_text_message")], self.sender, self.store, self.knowledge, None)
        self.assertEqual(offset, 810004)
        self.assertEqual(self.sender.sent, [])

    async def test_completed_duplicate_advances_offset_without_sending_again(self):
        update = payload("delivery_question")
        self.assertEqual(await process_batch([update], self.sender, self.store, self.knowledge, None), 810002)
        self.assertEqual(await process_batch([update], self.sender, self.store, self.knowledge, None), 810002)
        self.assertEqual(self.sender.sent, ["810001"])

    async def test_long_answer_does_not_block_next_update(self):
        updates = [payload("delivery_question"), payload("unknown_question")]
        offset = await process_batch(updates, self.sender, self.store, LongKnowledge(), None)
        self.assertEqual(offset, 810003)
        self.assertEqual(self.sender.sent, ["810001", "810002"])
