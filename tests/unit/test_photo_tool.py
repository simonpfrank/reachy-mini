"""photo: a private photo saved on the robot with its measured pose; the head is never moved."""

import asyncio
import importlib.util
import json
import stat
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from reachy_mini.utils import create_head_pose

TOOL = Path(__file__).resolve().parents[2] / "robot_tools" / "photo.py"


@pytest.fixture
def robot(monkeypatch, tmp_path):
    core = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
    core.Tool = type("Tool", (), {})
    core.ToolDependencies = types.SimpleNamespace
    monkeypatch.setitem(sys.modules, core.__name__, core)
    monkeypatch.setenv("REACHY_TOOLS_CAMERA_DIR", str(tmp_path / "camera"))
    spec = importlib.util.spec_from_file_location("_photo_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def no_wait(_seconds: float) -> None:
        pass

    monkeypatch.setattr(module.asyncio, "sleep", no_wait)
    tilted = create_head_pose(0, 0, 0.01, roll=12, pitch=-8, yaw=30)
    state = types.SimpleNamespace(pose=tilted, queued=[], jpeg=b"JPEG", wobble=[])
    status: dict[str, Any] = {"queue_size": 0}
    reachy = types.SimpleNamespace(
        get_current_head_pose=lambda: state.pose,
        disable_wobbling=lambda: state.wobble.append("off"),
        enable_wobbling=lambda: state.wobble.append("on"),
        get_current_joint_positions=lambda: ([np.radians(20.0), 0, 0, 0, 0, 0, 0], [0.1, -0.1]),
        media=types.SimpleNamespace(
            get_frame_jpeg=lambda: state.jpeg, camera=types.SimpleNamespace(resolution=(1280, 720))
        ),
    )
    manager = types.SimpleNamespace(get_status=lambda: status, queue_move=state.queued.append)
    deps = types.SimpleNamespace(reachy_mini=reachy, movement_manager=manager)
    return types.SimpleNamespace(module=module, deps=deps, state=state, status=status, dir=tmp_path / "camera")


def take(robot) -> dict[str, Any]:
    return asyncio.run(robot.module.Photo()(robot.deps))


def test_tilted_head_is_not_moved_and_its_measured_pose_is_recorded(robot):
    result = take(robot)
    assert result["saved"] is True
    assert robot.state.queued == []
    meta = json.loads((robot.dir / "photo.json").read_text())
    assert meta["head_deg"] == {"roll": pytest.approx(12.0), "pitch": pytest.approx(-8.0), "yaw": pytest.approx(30.0)}


def test_speech_wobble_is_off_while_the_photo_is_taken(robot):
    seen: list[list[str]] = []
    robot.deps.reachy_mini.media.get_frame_jpeg = lambda: seen.append(list(robot.state.wobble)) or b"JPEG"
    take(robot)
    assert seen == [["off"]] and robot.state.wobble == ["off", "on"]


def test_photo_and_pose_are_saved_owner_only_replacing_the_last(robot):
    take(robot)
    robot.state.jpeg = b"NEWER"
    take(robot)
    assert (robot.dir / "photo.jpg").read_bytes() == b"NEWER"
    meta = json.loads((robot.dir / "photo.json").read_text())
    assert set(meta) >= {"time", "head_deg", "body_yaw_deg", "resolution"}
    assert meta["resolution"] == [1280, 720] and meta["body_yaw_deg"] == pytest.approx(20.0)
    assert set(meta["head_deg"]) == {"roll", "pitch", "yaw"}
    for path in (robot.dir / "photo.jpg", robot.dir / "photo.json"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(robot.dir.stat().st_mode) == 0o700
    assert sorted(p.name for p in robot.dir.iterdir()) == ["photo.jpg", "photo.json"]


def test_refuses_while_the_robot_is_already_moving(robot):
    robot.status["queue_size"] = 2
    result = take(robot)
    assert "moving" in result["error"] and robot.state.queued == []
    assert not robot.dir.exists()


def test_no_frame_is_an_explicit_error_and_saves_nothing(robot):
    robot.state.jpeg = None
    assert "no frame" in take(robot)["error"].lower()
    assert not (robot.dir / "photo.jpg").exists()


def test_the_model_is_told_it_cannot_see_the_photo(robot):
    result = take(robot)
    assert "b64_im" not in result and "cannot see" in result["note"]
