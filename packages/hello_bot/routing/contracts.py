"""Classifier boundary, independent of Jev transport details."""

from typing import Protocol

from hello_bot.routing.models import IntentDecision


class IntentClassifier(Protocol):
    async def classify(self, text: str) -> IntentDecision: ...
