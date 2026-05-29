"""Tests for the launchd template substitution script."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHD_DIR = REPO_ROOT / "launchd"


def test_substitute_replaces_all_placeholders(tmp_path: Path) -> None:
    """substitute(template, context) returns the template with all {{X}}
    placeholders replaced; no {{ left in output."""
    from launchd.install_launchd import substitute

    template = (
        "<key>USER</key><string>{{USER}}</string>\n"
        "<key>HOME</key><string>{{HOME}}</string>\n"
        "<key>REPO_ROOT</key><string>{{REPO_ROOT}}</string>\n"
    )
    result = substitute(template, {"USER": "alice", "HOME": "/Users/alice",
                                   "REPO_ROOT": "/Users/alice/repo"})
    assert "{{" not in result
    assert "alice" in result
    assert "/Users/alice/repo" in result


def test_substitute_raises_on_missing_placeholder() -> None:
    """If the context is missing a placeholder used in the template,
    substitute raises KeyError with the missing key's name."""
    from launchd.install_launchd import substitute
    with pytest.raises(KeyError) as exc_info:
        substitute("hello {{MISSING}}", {})
    assert "MISSING" in str(exc_info.value)


def test_default_context_has_required_keys() -> None:
    """default_context() returns a dict with USER, HOME, REPO_ROOT, UV, LOG_DIR."""
    from launchd.install_launchd import default_context

    ctx = default_context(repo_root=Path("/tmp/test"))
    for key in ("USER", "HOME", "REPO_ROOT", "UV", "LOG_DIR"):
        assert key in ctx
        assert ctx[key]  # non-empty


def test_worker_template_substitutes_to_valid_xml(tmp_path: Path) -> None:
    """The committed worker template, when substituted, is well-formed XML
    that `plutil -lint` accepts as a valid plist."""
    from launchd.install_launchd import default_context, substitute

    template_path = LAUNCHD_DIR / "com.homephoto.worker.plist.template"
    if not template_path.exists():
        pytest.skip("worker template not yet created (Task 3)")
    rendered = substitute(template_path.read_text(),
                          default_context(repo_root=REPO_ROOT))
    out = tmp_path / "out.plist"
    out.write_text(rendered)
    result = subprocess.run(["plutil", "-lint", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"plutil rejected the plist: {result.stderr}"


def test_dashboard_template_substitutes_to_valid_xml(tmp_path: Path) -> None:
    from launchd.install_launchd import default_context, substitute

    template_path = LAUNCHD_DIR / "com.homephoto.dashboard.plist.template"
    if not template_path.exists():
        pytest.skip("dashboard template not yet created (Task 4)")
    rendered = substitute(template_path.read_text(),
                          default_context(repo_root=REPO_ROOT))
    out = tmp_path / "out.plist"
    out.write_text(rendered)
    result = subprocess.run(["plutil", "-lint", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"plutil rejected the plist: {result.stderr}"


def test_backup_template_substitutes_to_valid_xml(tmp_path: Path) -> None:
    from launchd.install_launchd import default_context, substitute

    template_path = LAUNCHD_DIR / "com.homephoto.backup.plist.template"
    if not template_path.exists():
        pytest.skip("backup template not yet created (Task 5)")
    rendered = substitute(template_path.read_text(),
                          default_context(repo_root=REPO_ROOT))
    out = tmp_path / "out.plist"
    out.write_text(rendered)
    result = subprocess.run(["plutil", "-lint", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"plutil rejected the plist: {result.stderr}"


def test_mlx_template_substitutes_to_valid_xml(tmp_path: Path) -> None:
    from launchd.install_launchd import default_context, substitute

    template_path = LAUNCHD_DIR / "com.homephoto.mlx.plist.template"
    if not template_path.exists():
        pytest.skip("mlx template not present (optional, Task 7)")
    rendered = substitute(template_path.read_text(),
                          default_context(repo_root=REPO_ROOT))
    out = tmp_path / "out.plist"
    out.write_text(rendered)
    result = subprocess.run(["plutil", "-lint", str(out)],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"plutil rejected: {result.stderr}"
