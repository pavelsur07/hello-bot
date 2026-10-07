import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DemoCliTests(unittest.TestCase):
    def test_demo_prints_ruble_sign_even_with_cp1251_default(self):
        environment = dict(os.environ, PYTHONIOENCODING="cp1251")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "apps" / "telegram_bot" / "main.py"),
                "--demo-update",
                "examples/demo_update.json",
                "--knowledge-dir",
                "examples/knowledge",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        self.assertIn("300 ₽", result.stdout.decode("utf-8"))
