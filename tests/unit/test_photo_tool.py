"""photo: a private, level photo saved on the robot with its pose; the previous pose is restored."""

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
from reachy_mini.utils.rotation import Rotation

TOOL = Path(__file__).resolve().parents[2] / "robot_tools" / "photo.py"


class FakeMove:
    """Stand-in for Pollen's GotoQueueMove that keeps its arguments."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@pytest.fixture
def robot(monkeypatch, tmp_path):
    core = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
    core.Tool = type("Tool", (), {})
    core.ToolDependencies = types.SimpleNamespace
    moves = types.ModuleType("reachy_mini_conversation_app.dance_emotion_moves")
    moves.GotoQueueMove = FakeMove
    monkeypatch.setitem(sys.modules, core.__name__, core)
    monkeypatch.setitem(sys.modules, moves.__name__, moves)
    monkeypatch.setenv("REACHY_TOOLS_CAMERA_DIR", str(tmp_path / "camera"))
    spec = importlib.util.spec_from_file_location("_photo_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def no_wait(_seconds: float) -> None:
        pass

    monkeypatch.setattr(module.asyncio, "sleep", no_wait)
    tilted = create_head_pose(0, 0, 0.01, roll=12, pitch=-8, yaw=30)
    state = types.SimpleNamespace(pose=tilted, queued=[], jpeg=b"JPEG", wobble=[])
    level_command = create_head_pose(0, 0, 0.01, roll=0, pitch=-8, yaw=30).tolist()
    status: dict[str, Any] = {"queue_size": 0, "last_commanded_pose": {"head": level_command}}
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


def angles(pose: np.ndarray) -> list[float]:
    return [round(float(a), 3) + 0.0 for a in Rotation.from_matrix(pose[:3, :3]).as_euler("xyz", degrees=True)]


def test_tilted_head_is_levelled_keeping_yaw_and_pitch_then_restored(robot):
    start = robot.state.pose
    result = take(robot)
    level, hold, back = robot.state.queued
    assert angles(level.kwargs["target_head_pose"]) == [0.0, -8.0, 30.0]
    assert hold.kwargs["target_head_pose"] is level.kwargs["target_head_pose"]
    assert back.kwargs["target_head_pose"] is start
    assert np.allclose(level.kwargs["target_head_pose"][:3, 3], start[:3, 3])
    assert all(m.kwargs["target_body_yaw"] == pytest.approx(np.radians(20.0)) for m in robot.state.queued)
    assert result["saved"] is True and result["levelled"] is True


def commanded(robot, *rolls: float) -> dict[str, float]:
    """Make the control loop report these commanded rolls in turn (then the last); queue size stays 0,
    as it does on the robot while queue_move is still in the app's command queue."""
    current = {"roll": rolls[0]}
    remaining = iter(rolls)

    def status() -> dict[str, Any]:
        current["roll"] = next(remaining, current["roll"])
        head = create_head_pose(0, 0, 0.01, roll=current["roll"], pitch=-8, yaw=30).tolist()
        return {"queue_size": 0, "last_commanded_pose": {"head": head}}

    robot.deps.movement_manager.get_status = status
    return current


def test_photo_waits_for_the_level_pose_even_while_the_queue_reads_empty(robot):
    current = commanded(robot, 12, 12, 7, 2, 0)  # the bug: queue size 0 before the moves were queued
    captured_at: list[float] = []
    robot.deps.reachy_mini.media.get_frame_jpeg = lambda: captured_at.append(current["roll"]) or b"JPEG"
    assert take(robot)["saved"] is True
    assert captured_at == [0]


def test_levelling_that_never_finishes_takes_no_photo(robot, monkeypatch):
    commanded(robot, 12)
    monkeypatch.setattr(robot.module, "MOVE_S", 0)
    monkeypatch.setattr(robot.module, "HOLD_S", 0)
    assert "did not finish levelling" in take(robot)["error"]
    assert not (robot.dir / "photo.jpg").exists()
    assert robot.state.wobble == ["off", "on"]


def test_speech_wobble_is_off_while_the_photo_is_taken(robot):
    seen: list[list[str]] = []
    robot.deps.reachy_mini.media.get_frame_jpeg = lambda: seen.append(list(robot.state.wobble)) or b"JPEG"
    take(robot)
    assert seen == [["off"]] and robot.state.wobble == ["off", "on"]


def test_level_head_is_not_moved(robot):
    robot.state.pose = create_head_pose(roll=0.4, pitch=5, yaw=-10)
    assert take(robot)["levelled"] is False
    assert robot.state.queued == []


def test_photo_and_pose_are_saved_owner_only_replacing_the_last(robot):
    take(robot)
    robot.state.jpeg = b"NEWER"
    take(robot)
    assert (robot.dir / "photo.jpg").read_bytes() == b"NEWER"
    meta = json.loads((robot.dir / "photo.json").read_text())
    assert set(meta) >= {"time", "head_deg", "body_yaw_deg", "levelled", "resolution"}
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
