"""scripts/hub.sh with real processes: start, status, restart and stop on a spare port. No mocks.

A spare port and a temporary state folder are used, so a hub already running on 8710 is never touched."""

import os
import socket
import subprocess
import types
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "hub.sh"


def free_port() -> int:
    with socket.socket() as spare:
        spare.bind(("127.0.0.1", 0))
        return int(spare.getsockname()[1])


@pytest.fixture
def hub(tmp_path: Path) -> Iterator[types.SimpleNamespace]:
    port = free_port()
    env = {**os.environ, "HUB_PORT": str(port), "HUB_STATE_DIR": str(tmp_path), "REACHY_HOST": "127.0.0.1"}

    def run(command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 -- fixed local script
            [str(SCRIPT), command], env=env, capture_output=True, text=True, check=False, timeout=30
        )

    yield types.SimpleNamespace(port=port, run=run)
    run("stop")


def page_status(port: int) -> int:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:  # noqa: S310 -- localhost
        return int(response.status)


def process_of(run: Callable[[str], subprocess.CompletedProcess[str]]) -> str:
    return run("status").stdout.split("process ")[1].split(")")[0]


def test_start_serves_the_page_and_stop_ends_it(hub: types.SimpleNamespace) -> None:
    started = hub.run("start")
    assert started.returncode == 0 and "Started" in started.stdout
    assert page_status(hub.port) == 200
    assert hub.run("status").returncode == 0
    stopped = hub.run("stop")
    assert stopped.returncode == 0 and "Stopped" in stopped.stdout
    assert hub.run("status").returncode == 1
    with pytest.raises(OSError):
        page_status(hub.port)


def test_starting_twice_keeps_one_hub(hub: types.SimpleNamespace) -> None:
    hub.run("start")
    first = process_of(hub.run)
    again = hub.run("start")
    assert again.returncode == 0 and "Already running" in again.stdout and process_of(hub.run) == first


def test_restart_gives_a_new_process_that_serves_the_page(hub: types.SimpleNamespace) -> None:
    hub.run("start")
    before = process_of(hub.run)
    restarted = hub.run("restart")
    assert restarted.returncode == 0 and process_of(hub.run) != before
    assert page_status(hub.port) == 200


def test_stopping_when_nothing_runs_is_not_an_error(hub: types.SimpleNamespace) -> None:
    result = hub.run("stop")
    assert result.returncode == 0 and "Not running" in result.stdout


def test_a_port_held_by_something_else_is_neither_used_nor_killed(hub: types.SimpleNamespace) -> None:
    with socket.socket() as other:
        other.bind(("127.0.0.1", hub.port))
        other.listen()
        started = hub.run("start")
        assert started.returncode != 0 and "in use" in started.stderr
        assert "Not running" in hub.run("stop").stdout  # and this test process is still alive to see it
        other.getsockname()
