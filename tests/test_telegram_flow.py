import json
import tempfile
import unittest
from pathlib import Path

from hello_bot.conversations.answer_from_knowledge import DeliveryStateError, FALLBACK, answer, process_update
from hello_bot.core import OutboundMessage
from hello_bot.knowledge.markdown import MarkdownKnowledge
from hello_bot.knowledge.models import KnowledgeHit
from hello_bot.storage.sqlite_events import SQLiteEventStore
from hello_bot.channels.telegram.adapter import parse_update


ROOT = Path(__file__).resolve().parents[1]
CASES = {case["name"]: case["update"] for case in json.loads((ROOT / "tests" / "fixtures" / "telegram_updates.json").read_text(encoding="utf-8"))["cases"]}


def payload(name: str) -> bytes:
    return json.dumps(CASES[name], ensure_ascii=False).encode("utf-8")


class FakeSender:
    def __init__(self):
        self.sent: list[OutboundMessage] = []
        self.fail_next = False

    def parse_event(self, update: bytes):
        return parse_update(update)

    async def send(self, message, response):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("simulated send error")
        self.sent.append(response)


class LongKnowledge:
    async def search(self, query, area=None, limit=5):
        return [KnowledgeHit("long-article", "examples/knowledge/long.md", "Длинный раздел", "Условие. " * 700, "Длинная статья", "support")]


class LongMetadataKnowledge:
    async def search(self, query, area=None, limit=5):
        return [KnowledgeHit("long-title", "examples/knowledge/long.md", "Раздел", "Сведения.", "Название " * 600, "support")]


class FailingMarkSent:
    def __init__(self, store):
        self.store = store

    async def claim(self, channel, event_id):
        return await self.store.claim(channel, event_id)

    async def mark_sent(self, channel, event_id):
        raise RuntimeError("database write failed")

    async def release(self, channel, event_id):
        await self.store.release(channel, event_id)


class TelegramFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.store = SQLiteEventStore(Path(self.directory.name, "events.sqlite3"))
        self.knowledge = MarkdownKnowledge(ROOT / "examples" / "knowledge")
        self.sender = FakeSender()

    async def asyncTearDown(self):
        self.store.close()
        self.directory.cleanup()

    async def test_delivery_answer_has_exact_source_reference(self):
        self.assertTrue(await process_update(payload("delivery_question"), self.sender, self.store, self.knowledge))
        self.assertIn("300 ₽", self.sender.sent[0].text)
        self.assertIn("Источник:", self.sender.sent[0].text)
        self.assertEqual(self.sender.sent[0].source_refs, ("examples/knowledge/delivery.md::Стоимость доставки",))

    async def test_repeated_update_does_not_send_twice(self):
        update = payload("delivery_question")
        self.assertTrue(await process_update(update, self.sender, self.store, self.knowledge))
        self.assertTrue(await process_update(update, self.sender, self.store, self.knowledge))
        self.assertEqual(len(self.sender.sent), 1)

    async def test_unknown_and_shared_word_questions_get_fallback(self):
        for name in ("unknown_question", "shared_word_without_answer"):
            self.assertTrue(await process_update(payload(name), self.sender, self.store, self.knowledge))
        self.assertEqual([message.text for message in self.sender.sent], [FALLBACK, FALLBACK])

    async def test_draft_is_never_used(self):
        update = dict(CASES["unknown_question"])
        update["message"] = dict(update["message"], text="Какие бонусы будут в программе?")
        self.assertTrue(await process_update(json.dumps(update, ensure_ascii=False).encode(), self.sender, self.store, self.knowledge))
        self.assertEqual(self.sender.sent[0].text, FALLBACK)

    async def test_send_failure_releases_claim_for_retry(self):
        self.sender.fail_next = True
        update = payload("delivery_question")
        self.assertFalse(await process_update(update, self.sender, self.store, self.knowledge))
        self.assertTrue(await process_update(update, self.sender, self.store, self.knowledge))
        self.assertEqual(len(self.sender.sent), 1)

    async def test_non_text_update_is_acknowledged_without_reply(self):
        self.assertTrue(await process_update(payload("non_text_message"), self.sender, self.store, self.knowledge))
        self.assertEqual(self.sender.sent, [])

    async def test_empty_knowledge_cannot_invent_answer(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            empty = MarkdownKnowledge(Path(directory))
            self.assertTrue(await process_update(payload("delivery_question"), self.sender, self.store, empty))
            self.assertEqual(self.sender.sent[0].text, FALLBACK)

    async def test_mark_sent_failure_after_send_does_not_release_claim(self):
        failing = FailingMarkSent(self.store)
        with self.assertRaises(DeliveryStateError):
            await process_update(payload("delivery_question"), self.sender, failing, self.knowledge)
        self.assertEqual(len(self.sender.sent), 1)
        self.assertFalse(await self.store.claim(parse_update(payload("delivery_question")).channel, "810001"))

    async def test_long_section_gets_safe_short_answer_with_source(self):
        message = parse_update(payload("delivery_question"))
        response = await answer(message, LongKnowledge())
        self.assertLessEqual(len(response.text), 4096)
        self.assertIn("слишком длинный", response.text)
        self.assertEqual(response.source_refs, ("examples/knowledge/long.md::Длинный раздел",))

    async def test_long_metadata_cannot_overflow_telegram_reply(self):
        message = parse_update(payload("delivery_question"))
        response = await answer(message, LongMetadataKnowledge())
        self.assertLessEqual(len(response.text), 4096)
        self.assertIn("examples/knowledge/long.md::Раздел", response.text)
        self.assertEqual(response.source_refs, ("examples/knowledge/long.md::Раздел",))
