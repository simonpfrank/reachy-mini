"""The real hub against the real robot. No mocks. Skips when the robot is not reachable."""

import os
import socket
import time

import pytest
from fastapi.testclient import TestClient

from reachy_hub.server import create_app
from reachy_hub.store import Store

ROBOT = os.environ.get("REACHY_HOST", "192.168.0.15")


def _reachable(port: int) -> bool:
    try:
        socket.create_connection((ROBOT, port), timeout=2).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _reachable(8000), reason="robot daemon not reachable")
def test_hub_connects_to_robot_and_serves_its_state() -> None:
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
    if _reachable(7860):
        assert snap["app_link"] == "connected"
