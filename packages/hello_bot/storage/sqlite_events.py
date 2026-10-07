"""Single-process SQLite store for Telegram update status."""

import sqlite3
from pathlib import Path

from hello_bot.core import Channel


class SQLiteEventStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, timeout=5)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "channel TEXT NOT NULL, external_event_id TEXT NOT NULL, "
            "status TEXT NOT NULL CHECK(status IN ('pending', 'sent')), "
            "PRIMARY KEY (channel, external_event_id))"
        )
        self._connection.commit()

    async def claim(self, channel: Channel, external_event_id: str) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                "INSERT OR IGNORE INTO events(channel, external_event_id, status) VALUES (?, ?, 'pending')",
                (channel.value, external_event_id),
            )
        return cursor.rowcount == 1

    async def mark_sent(self, channel: Channel, external_event_id: str) -> None:
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE events SET status = 'sent' WHERE channel = ? AND external_event_id = ? AND status = 'pending'",
                (channel.value, external_event_id),
            )
        if cursor.rowcount != 1:
            raise ValueError("Нельзя завершить событие без активного claim")

    async def release(self, channel: Channel, external_event_id: str) -> None:
        with self._connection:
            self._connection.execute(
                "DELETE FROM events WHERE channel = ? AND external_event_id = ? AND status = 'pending'",
                (channel.value, external_event_id),
            )

    async def recover_pending(self) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM events WHERE status = 'pending'")

    def close(self) -> None:
        self._connection.close()
