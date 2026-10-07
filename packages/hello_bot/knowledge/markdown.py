"""Small, rebuildable in-memory index for published Markdown sections."""

import re
from pathlib import Path

from hello_bot.knowledge.models import KnowledgeHit


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REQUIRED_FIELDS = {"id", "title", "area", "status"}
TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)
MAX_ID_LENGTH = 80
MAX_TITLE_LENGTH = 200
MAX_SECTION_TITLE_LENGTH = 200
MAX_SOURCE_PATH_LENGTH = 500


def _tokens(text: str) -> set[str]:
    return {token for token in TOKEN_PATTERN.findall(text.casefold()) if len(token) >= 3}


def _read_document(path: Path) -> tuple[dict[str, str], list[tuple[str, str]]]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"{path}: отсутствует frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError(f"{path}: не закрыт frontmatter") from exc

    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"{path}: некорректные метаданные")
        key = key.strip()
        if key in metadata:
            raise ValueError(f"{path}: повторное поле {key}")
        metadata[key] = value.strip()
    missing = REQUIRED_FIELDS - metadata.keys()
    if missing:
        raise ValueError(f"{path}: отсутствует {', '.join(sorted(missing))}")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", metadata["id"]):
        raise ValueError(f"{path}: некорректный id")
    if len(metadata["id"]) > MAX_ID_LENGTH or len(metadata["title"]) > MAX_TITLE_LENGTH:
        raise ValueError(f"{path}: слишком длинные метаданные")
    if metadata["area"] not in {"sales", "support", "general"}:
        raise ValueError(f"{path}: некорректный area")
    if metadata["status"] not in {"draft", "published"}:
        raise ValueError(f"{path}: некорректный status")

    sections: list[tuple[str, str]] = []
    heading: str | None = None
    body: list[str] = []
    for line in lines[end + 1 :]:
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(body).strip()))
            heading = line[3:].strip()
            if len(heading) > MAX_SECTION_TITLE_LENGTH:
                raise ValueError(f"{path}: слишком длинный заголовок раздела")
            body = []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(body).strip()))
    if metadata["status"] == "published" and (not sections or any(not title or not text for title, text in sections)):
        raise ValueError(f"{path}: опубликованный документ содержит пустой раздел")
    if len({title for title, _ in sections}) != len(sections):
        raise ValueError(f"{path}: повторный заголовок раздела")
    return metadata, sections


class MarkdownKnowledge:
    """Load published Markdown once, then search it without external services."""

    def __init__(self, root: Path):
        resolved_root = root.resolve()
        if not resolved_root.is_relative_to(REPOSITORY_ROOT):
            raise ValueError("Каталог знаний должен находиться внутри репозитория")
        if not resolved_root.is_dir():
            raise ValueError(f"Каталог знаний не найден: {root}")
        found: list[KnowledgeHit] = []
        ids: set[str] = set()
        for path in sorted(resolved_root.rglob("*.md")):
            if path.name == "README.md":
                continue
            metadata, sections = _read_document(path)
            document_id = metadata["id"]
            if document_id in ids:
                raise ValueError(f"Повторный id: {document_id}")
            ids.add(document_id)
            if metadata["status"] != "published":
                continue
            source_path = path.relative_to(REPOSITORY_ROOT).as_posix()
            if len(source_path) > MAX_SOURCE_PATH_LENGTH:
                raise ValueError(f"{path}: слишком длинный путь к источнику")
            found.extend(
                KnowledgeHit(
                    document_id=document_id,
                    source_path=source_path,
                    section_title=heading,
                    text=text,
                    title=metadata["title"],
                    area=metadata["area"],
                )
                for heading, text in sections
            )
        self.sections = tuple(found)

    async def search(self, query: str, area: str | None = None, limit: int = 5) -> list[KnowledgeHit]:
        query_tokens = _tokens(query)
        if len(query_tokens) < 2 or limit <= 0:
            return []
        ranked: list[tuple[int, KnowledgeHit]] = []
        for hit in self.sections:
            if area is not None and hit.area != area:
                continue
            heading_tokens = _tokens(hit.section_title)
            body_tokens = _tokens(hit.text)
            matched = query_tokens & (heading_tokens | body_tokens)
            if len(matched) < 2 or len(matched) * 2 < len(query_tokens):
                continue
            score = len(matched) + len(matched & heading_tokens)
            ranked.append((score, hit))
        ranked.sort(key=lambda item: (-item[0], item[1].source_path, item[1].section_title))
        return [hit for _, hit in ranked[:limit]]
