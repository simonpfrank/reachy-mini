"""Prevent retired patch deployment through both imported functions and standalone scripts."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from robot_tools import deploy_phase1, install_phase1, install_voice_look_lifecycle

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("installer", [install_phase1, install_voice_look_lifecycle])
def test_install_refuses_before_source_reads_or_backup_creation(installer, tmp_path, monkeypatch):
    read = Mock(side_effect=AssertionError("Retired installer must not read the app"))
    mkdir = Mock(side_effect=AssertionError("Retired installer must not create a backup"))
    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(Path, "mkdir", mkdir)
    with pytest.raises(RuntimeError, match="no-app-edits/update-survival"):
        installer.install(tmp_path / "missing-app", tmp_path / "backup")
    read.assert_not_called()
    mkdir.assert_not_called()


def test_phase1_historical_check_is_explicitly_retired_and_never_changes_source(tmp_path, monkeypatch):
    source = tmp_path / "main.py"
    source.write_text("x = 1\n")
    monkeypatch.setattr(install_phase1, "PATCHES", {"main.py": [("x = 1\n", "x = 2\n")]})
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    result = install_phase1.install(tmp_path, None)
    assert result["mode"] == "check" and result["changed"] == ["main.py"]
    assert result["retired"] is True and result["deployment_allowed"] is False
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert before == after


def test_imported_deployer_unconditionally_refuses():
    with pytest.raises(SystemExit, match="No robot calls or file changes"):
        deploy_phase1.main()


@pytest.mark.parametrize("script,flags", [
    ("install_phase1.py", ["--app-dir", "missing-app", "--backup-dir", "backup"]),
    ("install_voice_look_lifecycle.py", ["--app-main", "missing.py", "--backup-dir", "backup"]),
    ("deploy_phase1.py", []),
    ("deploy_phase1.py", ["--force"]),
])
def test_standalone_deployment_refuses_without_touching_files(script, flags, tmp_path):
    # Exercise the real script entry points, not only imported guards. All paths are disposable.
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("unchanged")
    result = subprocess.run(  # noqa: S603 -- fixed local scripts, no shell or network
        [sys.executable, str(ROOT / "robot_tools" / script), *flags],
        cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode != 0
    assert "Retired:" in result.stderr
    assert sorted(path.name for path in tmp_path.iterdir()) == ["keep.txt"]
    assert sentinel.read_text() == "unchanged"
