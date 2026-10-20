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
