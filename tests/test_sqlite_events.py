import tempfile
import unittest
from pathlib import Path

from hello_bot.core import Channel
from hello_bot.storage.sqlite_events import SQLiteEventStore

ROOT = Path(__file__).resolve().parents[1]


class SQLiteEventStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_claim_is_unique_across_connections(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory, "events.sqlite3")
            first = SQLiteEventStore(path)
            second = SQLiteEventStore(path)
            try:
                self.assertTrue(await first.claim(Channel.TELEGRAM, "1"))
                self.assertFalse(await second.claim(Channel.TELEGRAM, "1"))
                self.assertTrue(await second.claim(Channel.WEB, "1"))
            finally:
                first.close()
                second.close()

    async def test_sent_event_is_not_claimed_after_reopening(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory, "events.sqlite3")
            first = SQLiteEventStore(path)
            self.assertTrue(await first.claim(Channel.TELEGRAM, "1"))
            await first.mark_sent(Channel.TELEGRAM, "1")
            first.close()
            second = SQLiteEventStore(path)
            try:
                self.assertFalse(await second.claim(Channel.TELEGRAM, "1"))
                await second.release(Channel.TELEGRAM, "1")
                self.assertFalse(await second.claim(Channel.TELEGRAM, "1"))
            finally:
                second.close()

    async def test_release_allows_retry(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store = SQLiteEventStore(Path(directory, "events.sqlite3"))
            try:
                await store.claim(Channel.TELEGRAM, "1")
                await store.release(Channel.TELEGRAM, "1")
                self.assertTrue(await store.claim(Channel.TELEGRAM, "1"))
            finally:
                store.close()

    async def test_recover_pending_preserves_sent(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            store = SQLiteEventStore(Path(directory, "events.sqlite3"))
            try:
                await store.claim(Channel.TELEGRAM, "pending")
                await store.claim(Channel.TELEGRAM, "sent")
                await store.mark_sent(Channel.TELEGRAM, "sent")
                await store.recover_pending()
                self.assertTrue(await store.claim(Channel.TELEGRAM, "pending"))
                self.assertFalse(await store.claim(Channel.TELEGRAM, "sent"))
            finally:
                store.close()
