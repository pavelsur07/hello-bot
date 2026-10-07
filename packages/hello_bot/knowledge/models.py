"""A retrieved Markdown section with a stable source reference."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    document_id: str
    source_path: str
    section_title: str
    text: str
    title: str
    area: str
