"""Tests for the backup_postgres.sh script.

We don't run the real backup (would need Docker); just verify the script is
shell-valid and prints the expected commands in dry-run mode."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "backup_postgres.sh"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


@pytest.mark.skipif(not _have("bash"), reason="bash not installed")
def test_script_syntax_is_valid() -> None:
    """`bash -n` parses the script without errors."""
    assert SCRIPT.exists(), f"missing {SCRIPT}"
    result = subprocess.run(["bash", "-n", str(SCRIPT)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not _have("bash"), reason="bash not installed")
def test_dry_run_lists_pg_dumpall_command(tmp_path: Path) -> None:
    """`BACKUP_DRY_RUN=1 bash backup_postgres.sh` echoes the commands it
    would run instead of executing them; output must mention pg_dumpall."""
    env = dict(os.environ)
    env["BACKUP_DRY_RUN"] = "1"
    env["BACKUP_DIR"] = str(tmp_path)
    result = subprocess.run(["bash", str(SCRIPT)],
                            capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert "pg_dumpall" in result.stdout
    assert str(tmp_path) in result.stdout


@pytest.mark.skipif(not _have("bash"), reason="bash not installed")
def test_dry_run_lists_retention_pruning(tmp_path: Path) -> None:
    """Dry run should also mention removing old backups (rotation)."""
    env = dict(os.environ)
    env["BACKUP_DRY_RUN"] = "1"
    env["BACKUP_DIR"] = str(tmp_path)
    env["RETENTION_DAYS"] = "14"
    result = subprocess.run(["bash", str(SCRIPT)],
                            capture_output=True, text=True, env=env)
    assert result.returncode == 0
    assert "14" in result.stdout or "retention" in result.stdout.lower()
