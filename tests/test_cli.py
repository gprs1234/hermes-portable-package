from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "hermes_portable.cli", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_show_key_pool_template_is_json() -> None:
    result = run_cli("show-template", "key-pool")
    assert result.returncode == 0
    assert '"providers"' in result.stdout


def test_init_creates_local_files(tmp_path: Path) -> None:
    portable_home = tmp_path / "portable"
    hermes_home = tmp_path / "hermes"
    result = run_cli(
        "init",
        "--portable-home",
        str(portable_home),
        "--hermes-home",
        str(hermes_home),
    )
    assert result.returncode == 0
    assert (portable_home / "config.yaml").exists()
    assert (portable_home / "secrets.env").exists()
    assert (portable_home / "key_pool.json").exists()
    assert (hermes_home / "plan_registry").exists()
