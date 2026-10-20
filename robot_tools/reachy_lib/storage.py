"""Where tools keep photos and scans on the robot, and how they write them: owner-only, replaced atomically."""

import os
from pathlib import Path


def state_dir() -> Path:
    """Where tools keep their settings and remembered state: outside the repository and the app, so updates keep it."""
    return Path(os.environ.get("REACHY_TOOLS_STATE_DIR", "~/.config/reachy_tools")).expanduser()


def camera_dir() -> Path:
    """Where the one-off photo is kept: on the robot, outside the repository."""
    return Path(os.environ.get("REACHY_TOOLS_CAMERA_DIR", "~/.local/share/reachy-tools/camera")).expanduser()


def scan_dir() -> Path:
    """Where the latest room scan is kept."""
    return Path(os.environ.get("REACHY_TOOLS_SCAN_DIR", "~/.local/share/reachy-tools/scan")).expanduser()


def write_private(directory: Path, files: dict[str, bytes]) -> None:
    """Create ``directory`` (owner-only) and replace each named file in it, owner-only, via a temporary file.

    Args:
        directory: Folder to write into; created if missing.
        files: File name to contents.
    """
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    for name, data in files.items():
        temporary = directory / f".{name}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
        temporary.replace(directory / name)
