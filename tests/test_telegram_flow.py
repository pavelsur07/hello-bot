import json
import tempfile
import unittest
from email.message import Message
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError

from hello_bot.channels.telegram.adapter import TelegramAdapter, TelegramClient, parse_update
from hello_bot.conversations.answer_from_knowledge import (
    FALLBACK,
    DeliveryStateError,
    answer,
    process_update,
)
from hello_bot.core import Channel, InboundMessage, OutboundMessage
from hello_bot.knowledge.markdown import MarkdownKnowledge
from hello_bot.knowledge.models import KnowledgeHit
from hello_bot.storage.sqlite_events import SQLiteEventStore
from tests.fakes import FakeResponse

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    case["name"]: case["update"]
    for case in json.loads(
        (ROOT / "tests" / "fixtures" / "telegram_updates.json").read_text(encoding="utf-8")
    )["cases"]
}


def payload(name: str) -> bytes:
    return json.dumps(CASES[name], ensure_ascii=False).encode("utf-8")


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[OutboundMessage] = []
        self.fail_next = False

    def parse_event(self, update: bytes) -> InboundMessage | None:
        return parse_update(update)

    async def send(self, message, response):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("simulated send error")
        self.sent.append(response)


class LongKnowledge:
    async def search(self, query, area=None, limit=5):
        return [
            KnowledgeHit(
                "long-article",
                "examples/knowledge/long.md",
                "Длинный раздел",
                "Условие. " * 700,
                "Длинная статья",
                "support",
            )
        ]


class LongMetadataKnowledge:
    async def search(self, query, area=None, limit=5):
        return [
            KnowledgeHit(
                "long-title",
                "examples/knowledge/long.md",
                "Раздел",
                "Сведения.",
                "Название " * 600,
                "support",
            )
        ]


class FailingMarkSent:
    def __init__(self, store):
        self.store = store

    async def claim(self, channel, event_id):
        return await self.store.claim(channel, event_id)

    async def mark_sent(self, channel, event_id):
        raise RuntimeError("database write failed")

    async def release(self, channel, event_id):
        await self.store.release(channel, event_id)

    async def recover_pending(self):
        await self.store.recover_pending()

    async def has_pending(self):
        return await self.store.has_pending()


class TelegramFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_incomplete_response_keeps_delivery_pending(self):
        class BrokenResponse(FakeResponse):
            def read(self):
                raise IncompleteRead(b"partial synthetic response", 20)

        def opener(request, timeout):
            return BrokenResponse({})

        sender = TelegramAdapter(TelegramClient("test-token", opener=opener))
        with self.assertRaises(DeliveryStateError):
            await process_update(payload("delivery_question"), sender, self.store, self.knowledge)
        self.assertTrue(await self.store.has_pending())
        self.assertFalse(await self.store.claim(Channel.TELEGRAM, "810001"))

    async def test_http_server_error_keeps_delivery_pending(self):
        failure = HTTPError("https://example.test/test-token", 503, "test-token", Message(), None)

        def opener(request, timeout):
            raise failure

        try:
            sender = TelegramAdapter(TelegramClient("test-token", opener=opener))
            with self.assertRaises(DeliveryStateError):
                await process_update(
                    payload("delivery_question"), sender, self.store, self.knowledge
                )
            self.assertFalse(await self.store.claim(Channel.TELEGRAM, "810001"))
        finally:
            failure.close()

    async def test_invalid_send_envelope_is_not_retried(self):
        for body in ({}, {"ok": True, "result": None}, {"ok": "unexpected"}):

            def opener(request, timeout, body=body):
                return FakeResponse(body)

            sender = TelegramAdapter(TelegramClient("test-token", opener=opener))
            with self.subTest(body=body):
                with self.assertRaises(DeliveryStateError):
                    await process_update(
                        payload("delivery_question"), sender, self.store, self.knowledge
                    )
                self.assertFalse(await self.store.claim(Channel.TELEGRAM, "810001"))
                # Explicitly reset only this synthetic claim for the next test case.
                await self.store.release(Channel.TELEGRAM, "810001")

    async def test_uncertain_send_stops_without_releasing_claim(self):
        def opener(request, timeout):
            raise TimeoutError("test-token: unknown delivery")

        sender = TelegramAdapter(TelegramClient("test-token", opener=opener))
        with self.assertRaises(DeliveryStateError) as error:
            await process_update(payload("delivery_question"), sender, self.store, self.knowledge)
        self.assertNotIn("test-token", str(error.exception))
        self.assertFalse(await self.store.claim(Channel.TELEGRAM, "810001"))

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.store = SQLiteEventStore(Path(self.directory.name, "events.sqlite3"))
        self.knowledge = MarkdownKnowledge(ROOT / "examples" / "knowledge")
        self.sender = FakeSender()

    async def asyncTearDown(self):
        self.store.close()
        self.directory.cleanup()

    async def test_delivery_answer_has_exact_source_reference(self):
        self.assertTrue(
            await process_update(
                payload("delivery_question"), self.sender, self.store, self.knowledge
            )
        )
        self.assertIn("300 ₽", self.sender.sent[0].text)
        self.assertIn("Источник:", self.sender.sent[0].text)
        self.assertEqual(
            self.sender.sent[0].source_refs, ("examples/knowledge/delivery.md::Стоимость доставки",)
        )

    async def test_repeated_update_does_not_send_twice(self):
        update = payload("delivery_question")
        self.assertTrue(await process_update(update, self.sender, self.store, self.knowledge))
        self.assertTrue(await process_update(update, self.sender, self.store, self.knowledge))
        self.assertEqual(len(self.sender.sent), 1)

    async def test_unknown_and_shared_word_questions_get_fallback(self):
        for name in ("unknown_question", "shared_word_without_answer"):
            self.assertTrue(
                await process_update(payload(name), self.sender, self.store, self.knowledge)
            )
        self.assertEqual([message.text for message in self.sender.sent], [FALLBACK, FALLBACK])

    async def test_draft_is_never_used(self):
        update = dict(CASES["unknown_question"])
        update["message"] = dict(update["message"], text="Какие бонусы будут в программе?")
        self.assertTrue(
            await process_update(
                json.dumps(update, ensure_ascii=False).encode(),
                self.sender,
                self.store,
                self.knowledge,
            )
        )
        self.assertEqual(self.sender.sent[0].text, FALLBACK)

    async def test_send_failure_releases_claim_for_retry(self):
        self.sender.fail_next = True
        update = payload("delivery_question")
        self.assertFalse(await process_update(update, self.sender, self.store, self.knowledge))
        self.assertTrue(await process_update(update, self.sender, self.store, self.knowledge))
        self.assertEqual(len(self.sender.sent), 1)

    async def test_non_text_update_is_acknowledged_without_reply(self):
        self.assertTrue(
            await process_update(
                payload("non_text_message"), self.sender, self.store, self.knowledge
            )
        )
        self.assertEqual(self.sender.sent, [])

    async def test_empty_knowledge_cannot_invent_answer(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            empty = MarkdownKnowledge(Path(directory))
            self.assertTrue(
                await process_update(payload("delivery_question"), self.sender, self.store, empty)
            )
            self.assertEqual(self.sender.sent[0].text, FALLBACK)

    async def test_mark_sent_failure_after_send_does_not_release_claim(self):
        failing = FailingMarkSent(self.store)
        with self.assertRaises(DeliveryStateError):
            await process_update(payload("delivery_question"), self.sender, failing, self.knowledge)
        self.assertEqual(len(self.sender.sent), 1)
        self.assertFalse(await self.store.claim(Channel.TELEGRAM, "810001"))

    async def test_long_section_gets_safe_short_answer_with_source(self):
        message = parse_update(payload("delivery_question"))
        assert message is not None
        response = await answer(message, LongKnowledge())
        self.assertLessEqual(len(response.text), 4096)
        self.assertIn("слишком длинный", response.text)
        self.assertEqual(response.source_refs, ("examples/knowledge/long.md::Длинный раздел",))

    async def test_long_metadata_cannot_overflow_telegram_reply(self):
        message = parse_update(payload("delivery_question"))
        assert message is not None
        response = await answer(message, LongMetadataKnowledge())
        self.assertLessEqual(len(response.text), 4096)
        self.assertIn("examples/knowledge/long.md::Раздел", response.text)
        self.assertEqual(response.source_refs, ("examples/knowledge/long.md::Раздел",))
