"""Telegram update parsing and Bot API transport for a single polling bot."""

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from hello_bot.channels.contracts import DeliveryUncertainError
from hello_bot.core import Channel, InboundMessage, OutboundMessage


class TelegramApiError(RuntimeError):
    """Bot API returned an error without exposing the token URL."""


def parse_update(payload: bytes) -> InboundMessage | None:
    update = json.loads(payload)
    if not isinstance(update, dict):
        raise ValueError("Telegram update должен быть объектом")
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat", {})
    sender = message.get("from", {})
    if not isinstance(chat, dict) or not isinstance(sender, dict):
        raise ValueError("Telegram chat/from должны быть объектами")
    if (
        chat.get("type") != "private"
        or sender.get("is_bot")
        or not isinstance(message.get("text"), str)
    ):
        return None
    try:
        for value in (update["update_id"], sender["id"], chat["id"], message["date"]):
            if type(value) is not int or value < 0:
                raise ValueError("Некорректный идентификатор или дата")
        return InboundMessage(
            channel=Channel.TELEGRAM,
            external_event_id=str(update["update_id"]),
            external_user_id=str(sender["id"]),
            external_conversation_id=str(chat["id"]),
            text=message["text"],
            received_at=datetime.fromtimestamp(message["date"], tz=UTC),
        )
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
        raise ValueError("Telegram update содержит некорректные обязательные поля") from exc


class TelegramClient:
    def __init__(self, token: str, opener: Callable[..., Any] = urlopen) -> None:
        if not token:
            raise ValueError("Telegram token is required")
        self._token = token
        self._opener = opener

    def _request(self, method: str, data: dict[str, Any], timeout: int = 35) -> object:
        request = Request(
            f"https://api.telegram.org/bot{self._token}/{method}",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=timeout) as response:
                result = json.loads(response.read())
        except HTTPError as exc:
            if method == "sendMessage" and exc.code >= 500:
                raise DeliveryUncertainError("Неизвестен результат отправки Telegram") from None
            raise TelegramApiError(f"Telegram API вернул HTTP {exc.code}") from None
        except (OSError, HTTPException):
            if method == "sendMessage":
                raise DeliveryUncertainError("Неизвестен результат отправки Telegram") from None
            raise TelegramApiError("Telegram API недоступен") from None
        except (ValueError, UnicodeError):
            if method == "sendMessage":
                raise DeliveryUncertainError("Неизвестен результат отправки Telegram") from None
            raise TelegramApiError("Telegram API вернул некорректный JSON") from None
        if not isinstance(result, dict) or type(result.get("ok")) is not bool:
            if method == "sendMessage":
                raise DeliveryUncertainError("Неизвестен результат отправки Telegram")
            raise TelegramApiError("Telegram API вернул некорректный ответ")
        if result["ok"] is False:
            raise TelegramApiError("Telegram API отклонил запрос")
        return result.get("result")

    async def get_updates(self, offset: int | None) -> list[bytes]:
        data: dict[str, Any] = {"timeout": 20, "allowed_updates": ["message"]}
        if offset is not None:
            data["offset"] = offset
        result = await asyncio.to_thread(self._request, "getUpdates", data)
        if not isinstance(result, list):
            raise TelegramApiError("Telegram API вернул некорректные updates")
        return [json.dumps(update, ensure_ascii=False).encode("utf-8") for update in result]

    async def get_webhook_url(self) -> str:
        result = await asyncio.to_thread(self._request, "getWebhookInfo", {})
        if not isinstance(result, dict) or not isinstance(result.get("url"), str):
            raise TelegramApiError("Telegram API вернул некорректный статус webhook")
        url = result["url"]
        assert isinstance(url, str)
        return url

    async def send_message(self, chat_id: str, text: str) -> None:
        if not text or len(text) > 4096:
            raise ValueError("Telegram text must be between 1 and 4096 characters")
        result = await asyncio.to_thread(
            self._request, "sendMessage", {"chat_id": chat_id, "text": text}
        )
        if not isinstance(result, dict) or type(result.get("message_id")) is not int:
            raise DeliveryUncertainError("Неизвестен результат отправки Telegram")


class TelegramAdapter:
    def __init__(self, client: TelegramClient) -> None:
        self.client = client

    def parse_event(self, payload: bytes) -> InboundMessage | None:
        return parse_update(payload)

    async def send(self, message: InboundMessage, response: OutboundMessage) -> None:
        await self.client.send_message(message.external_conversation_id, response.text)
