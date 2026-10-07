"""Run the same verification pipeline locally and in CI; never call live APIs."""

import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(
    arguments: list[str], *, cwd: Path = ROOT, environment: dict[str, str] | None = None
) -> None:
    print("+ " + " ".join(arguments), flush=True)
    subprocess.run(arguments, cwd=cwd, env=environment, check=True)


def main() -> int:
    python = sys.executable
    for command in (
        [python, "-m", "ruff", "format", "--check", "."],
        [python, "-m", "ruff", "check", "."],
        [python, "-m", "mypy"],
        [python, "-m", "pip", "check"],
        [python, "-m", "unittest", "discover", "-s", "tests", "-v"],
    ):
        run(command)

    # Use a disposable directory; do not delete or overwrite a user's dist/ files.
    local = ROOT / ".local"
    local.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="check-", dir=local) as directory:
        workspace = Path(directory)
        artifacts = workspace / "dist"
        run([python, "-m", "build", "--no-isolation", "--outdir", str(artifacts)])
        wheels = list(artifacts.glob("*.whl"))
        if len(wheels) != 1 or len(list(artifacts.glob("*.tar.gz"))) != 1:
            raise RuntimeError("Expected one wheel and one source distribution")
        installation = workspace / "wheel-env"
        venv.create(installation, with_pip=True)
        installed_python = installation / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        environment.pop("TELEGRAM_BOT_TOKEN", None)
        run(
            [
                str(installed_python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                str(wheels[0]),
            ],
            environment=environment,
        )
        run(
            [
                str(installed_python),
                str(ROOT / "apps/telegram_bot/main.py"),
                "--demo-update",
                "examples/demo_update.json",
                "--knowledge-dir",
                "examples/knowledge",
            ],
            environment=environment,
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from None
