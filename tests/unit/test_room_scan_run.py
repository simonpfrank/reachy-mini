"""room_scan: one queued move through every stop and back, a photo at each stop, saved with its pose."""

import asyncio
import importlib.util
import json
import math
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from reachy_mini.utils import create_head_pose

TOOL = Path(__file__).resolve().parents[2] / "robot_tools" / "room_scan.py"


@pytest.fixture
def robot(monkeypatch, tmp_path):
    core = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
    core.Tool = type("Tool", (), {})
    core.ToolDependencies = types.SimpleNamespace
    monkeypatch.setitem(sys.modules, core.__name__, core)
    monkeypatch.setenv("REACHY_TOOLS_SCAN_DIR", str(tmp_path / "scan"))
    spec = importlib.util.spec_from_file_location("_room_scan_run_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def no_wait(_seconds: float) -> None:
        pass

    monkeypatch.setattr(module.asyncio, "sleep", no_wait)
    events: list[str] = []
    state = types.SimpleNamespace(frames=0, missing=set(), explode_on=None)

    def frame() -> bytes | None:
        index, state.frames = state.frames, state.frames + 1
        events.append("photo")
        if index == state.explode_on:
            raise OSError("camera gone")
        return None if index in state.missing else f"JPEG{index}".encode()

    pose = create_head_pose(0, 0, 0.01, roll=2, pitch=-3, yaw=10)
    reachy = types.SimpleNamespace(
        get_current_head_pose=lambda: pose,
        get_current_joint_positions=lambda: ([np.radians(5.0), 0, 0, 0, 0, 0, 0], [0.1, -0.1]),
        disable_wobbling=lambda: events.append("wobble_off"),
        enable_wobbling=lambda: events.append("wobble_on"),
        media=types.SimpleNamespace(get_frame_jpeg=frame, camera=types.SimpleNamespace(resolution=(1280, 720))),
    )
    queued: list = []
    status = {"queue_size": 0}
    manager = types.SimpleNamespace(
        get_status=lambda: status, queue_move=lambda move: (events.append("queue"), queued.append(move))
    )
    deps = types.SimpleNamespace(reachy_mini=reachy, movement_manager=manager)
    return types.SimpleNamespace(
        module=module, deps=deps, events=events, queued=queued, status=status, state=state, pose=pose,
        dir=tmp_path / "scan",
    )


def scan(robot, **env):
    settings = robot.module.ScanSettings.from_env({k: str(v) for k, v in env.items()})
    return asyncio.run(robot.module.run_scan(robot.deps, settings, "test"))


def heading_of(head) -> float:
    return math.degrees(math.atan2(head[1, 0], head[0, 0]))


def test_the_timeline_reaches_each_stop_before_its_photo_and_ends_at_the_start(robot):
    module = robot.module
    start = module.motion.snapshot(robot.deps.reachy_mini)
    poses = module.plan(module.ScanSettings())
    move, photo_times = module.build_scan(start, poses, settle_s=0.5)
    assert photo_times == sorted(photo_times) and len(photo_times) == len(poses)
    for pose, moment in zip(poses, photo_times, strict=True):
        head, _, body = move.evaluate(moment)
        assert math.degrees(body) == pytest.approx(pose.body_yaw_deg)
        assert heading_of(head) == pytest.approx(pose.body_yaw_deg + pose.head_yaw_deg, abs=1e-6) or abs(
            heading_of(head) - (pose.body_yaw_deg + pose.head_yaw_deg)
        ) == pytest.approx(360)
    head, _, body = move.evaluate(move.duration)
    assert np.allclose(head, robot.pose) and body == pytest.approx(start.body)
    assert move.duration > photo_times[-1]


def test_one_move_is_queued_with_the_wobble_off_around_every_photo(robot):
    result = scan(robot)
    assert len(robot.queued) == 1
    assert robot.events[0] == "wobble_off" and robot.events[1] == "queue" and robot.events[-1] == "wobble_on"
    assert robot.events.count("photo") == 7 == result["stops"]


def test_photos_and_a_manifest_are_saved_with_planned_and_measured_poses(robot):
    result = scan(robot)
    assert result["complete"] is True
    assert sorted(p.name for p in robot.dir.iterdir()) == ["scan.json"] + [f"scan_{i:02}.jpg" for i in range(7)]
    assert (robot.dir / "scan_03.jpg").read_bytes() == b"JPEG3"
    manifest = json.loads((robot.dir / "scan.json").read_text())
    assert manifest["reason"] == "test" and manifest["complete"] is True and manifest["resolution"] == [1280, 720]
    assert len(manifest["stops"]) == 7 and manifest["settings"]["overlap"] == 0.25
    first = manifest["stops"][0]
    assert first["file"] == "scan_00.jpg" and first["planned"]["body_yaw_deg"] == -125
    assert set(first["measured"]) == {"heading_deg", "body_yaw_deg", "pitch_deg", "roll_deg"}


def test_the_queued_move_ends_back_at_the_pose_the_scan_started_from(robot):
    scan(robot)
    move = robot.queued[0]
    head, _, body = move.evaluate(move.duration)
    assert np.allclose(head, robot.pose) and math.degrees(body) == pytest.approx(5.0)


def test_a_missing_frame_is_recorded_and_the_scan_is_incomplete(robot):
    robot.state.missing = {2}
    result = scan(robot)
    manifest = json.loads((robot.dir / "scan.json").read_text())
    assert result["complete"] is False and manifest["complete"] is False
    assert manifest["stops"][2]["file"] is None and not (robot.dir / "scan_02.jpg").exists()
    assert (robot.dir / "scan_03.jpg").exists()


def test_photos_left_by_a_longer_earlier_scan_are_removed(robot):
    robot.dir.mkdir(parents=True)
    (robot.dir / "scan_09.jpg").write_bytes(b"OLD")
    scan(robot)
    assert not (robot.dir / "scan_09.jpg").exists()


def test_a_camera_failure_still_restores_the_wobble_and_keeps_the_partial_scan(robot):
    robot.state.explode_on = 3
    with pytest.raises(OSError, match="camera gone"):
        scan(robot)
    assert robot.events[-1] == "wobble_on" and len(robot.queued) == 1
    manifest = json.loads((robot.dir / "scan.json").read_text())
    assert manifest["complete"] is False and len(manifest["stops"]) == 3


def test_the_tool_replies_at_once_and_refuses_a_second_scan_while_one_runs(robot):
    module = robot.module
    release = asyncio.Event

    async def scenario():
        gate = release()

        async def slow(*_args):
            await gate.wait()
            return {}

        module.run_scan = slow
        tool = module.RoomScan()
        first = await tool(robot.deps)
        second = await tool(robot.deps)
        gate.set()
        await robot.deps.movement_manager._room_scan_task
        return first, second

    first, second = asyncio.run(scenario())
    assert first["started"] is True and "cannot see" in first["note"]
    assert "already" in second["error"]


def test_the_tool_refuses_while_the_robot_is_moving(robot):
    robot.status["queue_size"] = 2
    result = asyncio.run(robot.module.RoomScan()(robot.deps))
    assert "moving" in result["error"] and robot.queued == []


def test_the_tool_describes_itself_without_fixed_phrases(robot):
    tool = robot.module.RoomScan
    assert tool.name == "room_scan" and tool.parameters_schema["required"] == []
    assert "cannot see" in tool.description
