"""Keys stored with scripts/keys.sh and read by the tools' key lookup, in this platform's real store. No mocks.

Runs against the macOS Keychain on a Mac and systemd-creds on the robot. A throwaway Keychain service and key
folder are used, so real keys are never touched."""

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "keys.sh"
sys.path.insert(0, str(ROOT / "robot_tools"))

from reachy_lib import keys as key_store  # noqa: E402

DUMMY = b"dummy-not-a-key"


def keys(*args: str, stdin: bytes | None = None) -> bytes:
    """Run scripts/keys.sh and return its output."""
    return subprocess.run([str(SCRIPT), *args], input=stdin, check=True, capture_output=True).stdout  # noqa: S603


@pytest.fixture
def isolated(tmp_path: Path) -> Iterator[Path]:
    """A throwaway key folder and Keychain service in the environment; the key is removed afterwards."""
    names = ("REACHY_TOOLS_KEYS_DIR", "REACHY_TOOLS_KEYCHAIN_SERVICE", "TAVILY_API_KEY")
    saved = {name: os.environ.get(name) for name in names}
    os.environ.pop("TAVILY_API_KEY", None)
    os.environ["REACHY_TOOLS_KEYS_DIR"] = str(tmp_path / "keys")
    os.environ["REACHY_TOOLS_KEYCHAIN_SERVICE"] = f"reachy-tools-test-{uuid.uuid4().hex[:8]}"
    yield tmp_path / "keys"
    subprocess.run([str(SCRIPT), "remove", "tavily"], capture_output=True, check=False)  # noqa: S603
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def test_a_key_added_with_keys_sh_is_read_by_the_tools_then_removed(isolated: Path) -> None:
    keys("add", "tavily", stdin=DUMMY + b"\n")
    assert key_store.get_key("tavily") == DUMMY.decode()
    assert b"OK" in keys("check", "tavily")
    keys("remove", "tavily")
    with pytest.raises(key_store.KeyNotSet):
        key_store.get_key("tavily")


def test_adding_again_replaces_the_key(isolated: Path) -> None:
    keys("add", "tavily", stdin=DUMMY + b"\n")
    keys("add", "tavily", stdin=b"second-dummy\n")
    assert key_store.get_key("tavily") == "second-dummy"


def test_storage_details_for_this_platform(isolated: Path) -> None:
    keys("add", "tavily", stdin=DUMMY + b"\n")
    if sys.platform == "darwin":
        listing = subprocess.run([str(SCRIPT), "list"], capture_output=True, check=False)  # noqa: S603
        assert listing.returncode != 0 and b"Keychain" in listing.stderr
        refused = subprocess.run([str(SCRIPT), "add", "tavily"], input=b'bad"key\n', capture_output=True, check=False)  # noqa: S603
        assert refused.returncode != 0
        assert key_store.get_key("tavily") == DUMMY.decode()  # the refused key did not replace it
    else:
        cred = isolated / "tavily.cred"
        assert DUMMY not in cred.read_bytes() and cred.stat().st_mode & 0o077 == 0
        assert keys("list") == b"tavily\n"
