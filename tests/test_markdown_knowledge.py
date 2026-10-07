import json
import tempfile
import unittest
from pathlib import Path

from hello_bot.knowledge.markdown import MarkdownKnowledge

ROOT = Path(__file__).resolve().parents[1]
DEMO_KNOWLEDGE = ROOT / "examples" / "knowledge"
CASES = json.loads(
    (ROOT / "tests" / "fixtures" / "telegram_updates.json").read_text(encoding="utf-8")
)["cases"]


class MarkdownKnowledgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_repository_root_supports_installed_package(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            knowledge_dir = repository / "knowledge"
            knowledge_dir.mkdir()
            content = (DEMO_KNOWLEDGE / "delivery.md").read_text(encoding="utf-8")
            (knowledge_dir / "delivery.md").write_text(content, encoding="utf-8")
            knowledge = MarkdownKnowledge(knowledge_dir, repository_root=repository)
            hits = await knowledge.search("Стоимость доставки по городу")
            self.assertEqual(hits[0].source_path, "knowledge/delivery.md")

    async def test_finds_published_delivery_section_with_stable_source_path(self):
        hits = await MarkdownKnowledge(DEMO_KNOWLEDGE).search("Какая стоимость доставки по городу?")
        self.assertEqual(hits[0].document_id, "demo-delivery")
        self.assertEqual(hits[0].section_title, "Стоимость доставки")
        self.assertEqual(hits[0].source_path, "examples/knowledge/delivery.md")

    async def test_draft_and_readme_are_not_searchable(self):
        knowledge = MarkdownKnowledge(DEMO_KNOWLEDGE)
        self.assertEqual(await knowledge.search("Какие бонусы будут в программе?"), [])
        self.assertTrue(all("README.md" not in hit.source_path for hit in knowledge.sections))

    async def test_unknown_and_shared_word_questions_have_no_answer(self):
        knowledge = MarkdownKnowledge(DEMO_KNOWLEDGE)
        for name in ("unknown_question", "shared_word_without_answer"):
            question = next(
                case["update"]["message"]["text"] for case in CASES if case["name"] == name
            )
            with self.subTest(name=name):
                self.assertEqual(await knowledge.search(question), [])

    async def test_area_filter(self):
        knowledge = MarkdownKnowledge(DEMO_KNOWLEDGE)
        self.assertEqual(
            await knowledge.search("Сколько стоит набор открыток?", area="support"), []
        )
        self.assertEqual(
            (await knowledge.search("Сколько стоит набор открыток?", area="sales"))[0].document_id,
            "demo-pricing",
        )

    async def test_duplicate_id_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            first = (DEMO_KNOWLEDGE / "delivery.md").read_text(encoding="utf-8")
            Path(directory, "first.md").write_text(first, encoding="utf-8")
            Path(directory, "second.md").write_text(first, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "id"):
                MarkdownKnowledge(Path(directory))

    async def test_invalid_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            Path(directory, "bad.md").write_text(
                "---\nid: bad\nstatus: published\n---\n\n# Bad\n\n## Info\n\nText", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "title"):
                MarkdownKnowledge(Path(directory))

    async def test_oversized_source_metadata_is_rejected(self):
        for field, replacement in (("title", "Название " * 100), ("heading", "Раздел " * 100)):
            with self.subTest(field=field), tempfile.TemporaryDirectory(dir=ROOT) as directory:
                content = (DEMO_KNOWLEDGE / "delivery.md").read_text(encoding="utf-8")
                if field == "title":
                    content = content.replace("title: Доставка", f"title: {replacement}")
                else:
                    content = content.replace("## Стоимость доставки", f"## {replacement}")
                Path(directory, "too-long.md").write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "слишком длин"):
                    MarkdownKnowledge(Path(directory))

    async def test_knowledge_outside_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "репозитория"):
                MarkdownKnowledge(Path(directory))
