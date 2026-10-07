"""Search boundary for published Markdown knowledge."""

from typing import Protocol

from hello_bot.knowledge.models import KnowledgeHit


class KnowledgeSearch(Protocol):
    async def search(
        self, query: str, area: str | None = None, limit: int = 5
    ) -> list[KnowledgeHit]: ...
