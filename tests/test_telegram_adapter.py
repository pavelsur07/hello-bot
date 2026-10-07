import json
import unittest
from datetime import timezone
from pathlib import Path

from hello_bot.channels.telegram.adapter import TelegramAdapter, TelegramApiError, TelegramClient, parse_update
from hello_bot.core import Channel, OutboundMessage


ROOT = Path(__file__).resolve().parents[1]
CASES = {case["name"]: case["update"] for case in json.loads((ROOT / "tests" / "fixtures" / "telegram_updates.json").read_text(encoding="utf-8"))["cases"]}


def payload(name: str) -> bytes:
    return json.dumps(CASES[name], ensure_ascii=False).encode("utf-8")


class FakeResponse:
    def __init__(self, body: dict):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.body


class TelegramAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_parses_private_text_update(self):
        message = parse_update(payload("delivery_question"))
        self.assertEqual(message.channel, Channel.TELEGRAM)
        self.assertEqual(message.external_event_id, "810001")
        self.assertEqual(message.external_user_id, "410001")
        self.assertEqual(message.external_conversation_id, "410001")
        self.assertEqual(message.text, "Какая стоимость доставки по городу?")
        self.assertEqual(message.received_at.tzinfo, timezone.utc)

    async def test_ignores_non_text_group_and_bot_messages(self):
        self.assertIsNone(parse_update(payload("non_text_message")))
        group = json.loads(payload("delivery_question"))
        group["message"]["chat"]["type"] = "group"
        self.assertIsNone(parse_update(json.dumps(group).encode()))
        bot = json.loads(payload("delivery_question"))
        bot["message"]["from"]["is_bot"] = True
        self.assertIsNone(parse_update(json.dumps(bot).encode()))

    async def test_send_uses_telegram_api_without_network(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return FakeResponse({"ok": True, "result": {"message_id": 1}})

        adapter = TelegramAdapter(TelegramClient("test-token", opener=opener))
        await adapter.send(parse_update(payload("delivery_question")), OutboundMessage("Ответ"))
        self.assertEqual(len(requests), 1)
        self.assertTrue(requests[0][0].full_url.endswith("/sendMessage"))
        self.assertEqual(json.loads(requests[0][0].data)["chat_id"], "410001")
        self.assertEqual(json.loads(requests[0][0].data)["text"], "Ответ")

    async def test_get_updates_preserves_update_ids(self):
        def opener(request, timeout):
            self.assertTrue(request.full_url.endswith("/getUpdates"))
            self.assertEqual(json.loads(request.data)["offset"], 810001)
            return FakeResponse({"ok": True, "result": [CASES["delivery_question"]]})

        client = TelegramClient("test-token", opener=opener)
        updates = await client.get_updates(810001)
        self.assertEqual(json.loads(updates[0])["update_id"], 810001)

    async def test_api_error_does_not_leak_token(self):
        def opener(request, timeout):
            return FakeResponse({"ok": False, "description": "rejected"})

        client = TelegramClient("secret-token", opener=opener)
        with self.assertRaises(TelegramApiError) as error:
            await client.send_message("1", "hello")
        self.assertNotIn("secret-token", str(error.exception))

    async def test_webhook_status_prevents_polling_conflict(self):
        def opener(request, timeout):
            self.assertTrue(request.full_url.endswith("/getWebhookInfo"))
            return FakeResponse({"ok": True, "result": {"url": "https://example.test/hook"}})

        client = TelegramClient("test-token", opener=opener)
        self.assertEqual(await client.get_webhook_url(), "https://example.test/hook")
