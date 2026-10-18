"""The real hub against the real robot. No mocks. Fails, saying what to start, when the daemon or app is down."""

import os
import socket
import time

import pytest
from fastapi.testclient import TestClient

from reachy_hub.server import create_app
from reachy_hub.store import Store

ROBOT = os.environ.get("REACHY_HOST", "192.168.0.15")


def _require(port: int, what: str) -> None:
    try:
        socket.create_connection((ROBOT, port), timeout=2).close()
    except OSError:
        pytest.fail(f"{what} not reachable at {ROBOT}:{port}; start it and rerun")


def test_hub_connects_to_robot_and_serves_its_state() -> None:
    _require(8000, "robot daemon")
    _require(7860, "conversation app")
    with TestClient(create_app(Store(), robot_host=ROBOT)) as client:
        deadline = time.time() + 8
        snap = client.get("/api/snapshot").json()
        ready = lambda s: s["robot"] and all(s[k] == "connected" for k in ("robot_link", "imu_link", "log_link"))  # noqa: E731
        while time.time() < deadline and not ready(snap):
            time.sleep(0.25)
            snap = client.get("/api/snapshot").json()
    assert snap["robot_link"] == "connected"
    assert snap["imu_link"] == "connected"
    assert snap["log_link"] == "connected"
    assert snap["robot"]["motor_mode"] in {"enabled", "disabled", "gravity_compensation"}
    assert snap["app_link"] == "connected"
