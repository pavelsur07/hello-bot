"""Separate decision and text-generation capabilities."""

from collections.abc import Sequence
from typing import Protocol

from hello_bot.routing.models import IntentDecision


class DecisionModel(Protocol):
    """Jev can implement this capability."""

    async def classify_intent(self, text: str) -> IntentDecision: ...


class TextGenerator(Protocol):
    """OpenAI and Kimi adapters can implement this capability."""

    async def generate(self, question: str, context: Sequence[str]) -> str: ...
