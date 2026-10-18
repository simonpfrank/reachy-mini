"""Wake watcher and sleep tool against the real robot: daemon, shared mic, wake model and systemd. No mocks.
Fails, saying what to set up, when the daemon, app or wake venv is missing."""

import socket
import subprocess

import pytest

from reachy_wake import watcher
from robot_tools import sleep


def _require(port: int, what: str) -> None:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=2).close()
    except OSError:
        pytest.fail(f"{what} not reachable at 127.0.0.1:{port}; start it and rerun")


def test_daemon_reports_the_running_app() -> None:
    _require(8000, "robot daemon")
    _require(7860, "conversation app")
    assert watcher.app_running() is True


def test_shared_mic_gives_frames_while_the_app_also_listens() -> None:
    mic = watcher.open_mic()
    try:
        assert mic.stdout is not None
        audio = watcher.frames(mic.stdout)
        got = [next(audio) for _ in range(5)]
    finally:
        mic.terminate()
        mic.wait(timeout=5)
    assert all(len(f) == watcher.FRAME and str(f.dtype) == "int16" for f in got)


def test_wake_model_loads_in_its_venv_and_ignores_silence() -> None:
    if not sleep.WAKE_PYTHON.exists():
        pytest.fail(f"wake venv missing: {sleep.WAKE_PYTHON}; see docs/development_setup.md")
    code = (
        "import numpy as np; from reachy_wake.watcher import WakeWord, FRAME; "
        "w = WakeWord(); print([w(np.zeros(FRAME, dtype=np.int16)) for _ in range(10)])"
    )
    command = [str(sleep.WAKE_PYTHON), "-c", code]
    result = subprocess.run(command, cwd=sleep.ROOT, capture_output=True, text=True, timeout=60)  # noqa: S603
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str([None] * 10)


def test_systemd_user_units_start_without_a_login_session() -> None:
    env = {k: v for k, v in sleep.user_env().items() if k != "DBUS_SESSION_BUS_ADDRESS"}
    result = subprocess.run(
        ["/usr/bin/systemd-run", "--user", "--collect", "--quiet", "/usr/bin/true"],
        env=env, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
