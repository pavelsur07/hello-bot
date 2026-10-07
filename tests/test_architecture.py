"""Guard the documented import boundaries without another runtime dependency."""

import ast
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages" / "hello_bot"
ALLOWED_PEERS = {
    "core": set(),
    "channels": {"core"},
    "storage": {"core"},
    "knowledge": {"core"},
    "routing": {"core", "ai"},
    "ai": {"core", "routing"},
    "conversations": {"core", "channels", "storage", "knowledge", "routing", "ai"},
}
DOMAIN_STDLIB = {"typing", "collections", "dataclasses", "enum", "datetime", "math", "__future__"}


def imports(path: Path) -> list[str]:
    relative = path.relative_to(PACKAGE)
    parts = ["hello_bot", *relative.with_suffix("").parts]
    package = ".".join(parts[:-1])
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if node.level:
                name = importlib.util.resolve_name("." * node.level + name, package)
            names.append(name)
            if node.module is None:
                names.extend(f"{name}.{alias.name}" for alias in node.names)
    return names


class ArchitectureTests(unittest.TestCase):
    def test_domain_and_contracts_do_not_import_infrastructure(self):
        for path in PACKAGE.rglob("*.py"):
            relative = path.relative_to(PACKAGE)
            domain = relative.parts[0] == "core" or path.name in {"models.py", "contracts.py"}
            for name in imports(path):
                if (domain or relative.parts[0] == "conversations") and not name.startswith(
                    "hello_bot"
                ):
                    with self.subTest(path=relative, imported=name):
                        self.assertIn(name.split(".")[0], DOMAIN_STDLIB)
                if domain and name.startswith("hello_bot"):
                    with self.subTest(path=relative, imported=name):
                        self.assertTrue(
                            name == "hello_bot.core"
                            or name.startswith("hello_bot.core.")
                            or name.endswith((".models", ".contracts")),
                            "Domain code imports a concrete adapter",
                        )

    def test_cross_module_imports_follow_dependency_table(self):
        for path in PACKAGE.rglob("*.py"):
            relative = path.relative_to(PACKAGE)
            owner = relative.parts[0]
            if owner not in ALLOWED_PEERS:
                continue
            for name in imports(path):
                if not name.startswith("hello_bot."):
                    continue
                dependency = name.split(".")[1]
                with self.subTest(path=relative, imported=name):
                    self.assertIn(dependency, ALLOWED_PEERS[owner] | {owner})
                    if owner == "routing" and dependency == "ai":
                        self.assertEqual(name, "hello_bot.ai.contracts")
                    if owner == "ai" and dependency == "routing":
                        self.assertEqual(name, "hello_bot.routing.models")
                    if owner == "conversations" and dependency != owner:
                        self.assertTrue(
                            dependency == "core" or name.endswith((".contracts", ".models")),
                            "Conversation imports a concrete adapter",
                        )
