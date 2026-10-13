"""Real connections to the robot. No mocks. Skips when the robot or app is not reachable.

Set REACHY_HOST to override the robot address.
"""

import asyncio
import os
import socket
from datetime import UTC, datetime

import pytest

from reachy_hub.events import Event, event_from_rpc, robot_state_from_full
from reachy_hub.sources import read_websocket

ROBOT = os.environ.get("REACHY_HOST", "192.168.0.15")
STATE_URL = f"ws://{ROBOT}:8000/api/state/ws/full?frequency=5&with_doa=true&with_imu=true"
APP_RPC_URL = f"ws://{ROBOT}:7860/rpc"


def _reachable(port: int) -> bool:
    try:
        socket.create_connection((ROBOT, port), timeout=2).close()
        return True
    except OSError:
        return False


def _collect(url: str, keep: int, accept: type | None = None, timeout_s: float = 15) -> tuple[list[object], list[str]]:
    """Read from ``url`` until ``keep`` messages are collected or the timeout passes."""
    messages: list[object] = []
    statuses: list[str] = []
    stop = asyncio.Event()

    def on_message(message: object) -> None:
        messages.append(message)
        if len(messages) >= keep:
            stop.set()

    async def run() -> None:
        try:
            await asyncio.wait_for(read_websocket(url, on_message, statuses.append, stop), timeout_s)
        except TimeoutError:
            pass

    asyncio.run(run())
    return messages, statuses


@pytest.mark.skipif(not _reachable(8000), reason="robot daemon not reachable")
def test_daemon_state_stream_gives_robot_states() -> None:
    messages, statuses = _collect(STATE_URL, keep=3)
    states = [robot_state_from_full(m) for m in messages if isinstance(m, dict)]
    assert statuses[0] == "connected"
    assert len(states) == 3
    assert all(s.motor_mode in {"enabled", "disabled", "gravity_compensation"} for s in states)


@pytest.mark.skipif(not _reachable(7860), reason="conversation app not running")
def test_app_rpc_stream_gives_app_events() -> None:
    messages, statuses = _collect(APP_RPC_URL, keep=3, timeout_s=10)
    events = [event_from_rpc(m, datetime.now(UTC)) for m in messages]
    assert statuses[0] == "connected"
    assert events and all(isinstance(e, Event) and e.kind.startswith("conversation.") for e in events)
