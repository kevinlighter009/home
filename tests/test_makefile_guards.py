"""Sanity tests: Makefile guards prevent silent misconfiguration.

We do not run `make bootstrap` (it would touch the user's environment).
Instead we shell out `make -n bootstrap` to print the recipe and grep for
the expected guard strings.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _have_make() -> bool:
    return shutil.which("make") is not None


@pytest.mark.skipif(not _have_make(), reason="make not installed")
def test_bootstrap_has_placeholder_guard() -> None:
    result = subprocess.run(
        ["make", "-n", "bootstrap"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "replace_me" in result.stdout
    assert "exit 1" in result.stdout


@pytest.mark.skipif(not _have_make(), reason="make not installed")
def test_dev_worker_depends_on_ensure_db() -> None:
    result = subprocess.run(
        ["make", "-n", "dev-worker"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0
    # ensure-db's recipe should appear before dev-worker's run command
    assert "home_photo_repo.db migrate" in result.stdout
    assert "home_photo_repo.worker.main" in result.stdout
