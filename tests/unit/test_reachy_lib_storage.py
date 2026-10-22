"""reachy_lib.storage: where photos and scans are kept, and owner-only writing."""

import stat
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "robot_tools"


@pytest.fixture
def storage(monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    sys.modules.pop("reachy_lib.storage", None)
    from reachy_lib import storage as module

    return module


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_files_and_folder_are_owner_only(storage, tmp_path):
    folder = tmp_path / "scan"
    storage.write_private(folder, {"a.jpg": b"AAA", "a.json": b"{}"})
    assert (folder / "a.jpg").read_bytes() == b"AAA"
    assert mode(folder) == 0o700 and mode(folder / "a.jpg") == 0o600 and mode(folder / "a.json") == 0o600


def test_existing_files_are_replaced_and_no_temporary_files_remain(storage, tmp_path):
    storage.write_private(tmp_path, {"a.jpg": b"OLD"})
    storage.write_private(tmp_path, {"a.jpg": b"NEW"})
    assert (tmp_path / "a.jpg").read_bytes() == b"NEW"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.jpg"]


def test_folders_default_under_the_tools_data_folder_and_can_be_overridden(storage, monkeypatch, tmp_path):
    monkeypatch.delenv("REACHY_TOOLS_CAMERA_DIR", raising=False)
    monkeypatch.delenv("REACHY_TOOLS_SCAN_DIR", raising=False)
    assert storage.camera_dir() == Path("~/.local/share/reachy-tools/camera").expanduser()
    assert storage.scan_dir() == Path("~/.local/share/reachy-tools/scan").expanduser()
    monkeypatch.setenv("REACHY_TOOLS_CAMERA_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("REACHY_TOOLS_SCAN_DIR", str(tmp_path / "s"))
    assert storage.camera_dir() == tmp_path / "c" and storage.scan_dir() == tmp_path / "s"


def test_the_state_folder_defaults_outside_the_repository_and_can_be_overridden(storage, monkeypatch, tmp_path):
    monkeypatch.delenv("REACHY_TOOLS_STATE_DIR", raising=False)
    assert storage.state_dir() == Path("~/.config/reachy_tools").expanduser()
    monkeypatch.setenv("REACHY_TOOLS_STATE_DIR", str(tmp_path / "state"))
    assert storage.state_dir() == tmp_path / "state"


def test_no_tool_works_out_the_state_folder_for_itself():
    """One definition, in reachy_lib.storage: a tool that reads the setting itself is a copy to remove."""
    copies = [p.name for p in TOOLS.glob("*.py") if "REACHY_TOOLS_STATE_DIR" in p.read_text()]
    assert copies == []


def test_the_models_folder_defaults_outside_the_repository_and_can_be_overridden(storage, monkeypatch, tmp_path):
    monkeypatch.delenv("REACHY_TOOLS_MODELS_DIR", raising=False)
    assert storage.models_dir() == Path("~/.local/share/reachy-tools/models").expanduser()
    monkeypatch.setenv("REACHY_TOOLS_MODELS_DIR", str(tmp_path / "m"))
    assert storage.models_dir() == tmp_path / "m"
