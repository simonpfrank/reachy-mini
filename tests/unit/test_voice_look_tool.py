"""Stock-app voice following: cancellable lifetime, safe poses, and queue arbitration."""

import asyncio
import importlib.util
import math
import sys
import threading
import types
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

TOOL = Path(__file__).resolve().parents[2] / "robot_tools" / "voice_look.py"


@pytest.fixture
def runtime(monkeypatch):
    core = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
    core.Tool = type("Tool", (), {})
    core.ToolDependencies = types.SimpleNamespace
    moves = types.ModuleType("reachy_mini_conversation_app.moves")
    moves.BreathingMove = type("BreathingMove", (), {"__init__": lambda self, *args: None})
    monkeypatch.setitem(sys.modules, core.__name__, core)
    monkeypatch.setitem(sys.modules, moves.__name__, moves)
    status = {"breathing_active": True, "queue_size": 0}
    deps = types.SimpleNamespace(
        movement_manager=types.SimpleNamespace(get_status=lambda: status, queue_move=Mock()), reachy_mini=Mock()
    )
    state = {"speaking": False}
    loaded = []

    def load():
        spec = importlib.util.spec_from_file_location(f"_stock_voice_test_{len(loaded)}", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setattr(module, "POLL_S", 0.001)
        monkeypatch.setattr(module, "_read_doa", lambda: None)
        loaded.append(module)
        return module

    return deps, load, state, status


def test_import_and_reload_have_no_worker_side_effects(runtime, monkeypatch):
    deps, load, *_ = runtime
    monkeypatch.setattr(threading.Thread, "start", Mock(side_effect=AssertionError("Import must not start threads")))
    load()
    load()
    assert not hasattr(deps.movement_manager, "_stock_voice_follower")


@pytest.mark.asyncio
async def test_one_app_owned_task_survives_tool_reload_and_stops_cleanly(runtime):
    deps, load, *_ = runtime
    first = asyncio.create_task(load().VoiceLook()(deps, enabled=True))
    try:
        for _ in range(20):
            await asyncio.sleep(0.005)
            if getattr(deps.movement_manager, "_stock_voice_follower", None):
                break
        owner = deps.movement_manager._stock_voice_follower
        assert owner.task is first and owner.running
        reloaded = load().VoiceLook()
        duplicate = await reloaded(deps, enabled=True)
        assert duplicate["running"] and owner.task is first
        result = await reloaded(deps, enabled=False)
        assert result == {"enabled": False, "running": False}
        await first
        assert not owner.running
    finally:
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)


@pytest.mark.asyncio
async def test_app_manager_cancellation_ends_worker(runtime):
    deps, load, *_ = runtime
    task = asyncio.create_task(load().VoiceLook()(deps, enabled=True))
    await asyncio.sleep(0.025)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not deps.movement_manager._stock_voice_follower.running


@pytest.mark.asyncio
async def test_robot_speaking_flag_comes_from_the_movement_manager(runtime, monkeypatch):
    deps, load, *_ = runtime
    module = load()
    seen = []

    async def step(follower, state, now):
        seen.append(state["speaking"])
        follower.running = False

    monkeypatch.setattr(module.StockFollower, "step", step)
    deps.movement_manager._is_speaking = True
    await module.VoiceLook()(deps, enabled=True)
    assert seen == [True]


@pytest.mark.parametrize(
    "requested,body,expected",
    [
        (100, 0, (100, 65)),
        (-100, 0, (-100, -65)),
        (200, 0, (-160, -125)),
        (-185, 0, (175, 140)),
        (180, -125, (175, 140)),
        (15, 0, (15, 0)),
    ],
)
def test_circular_reachable_turn_planning(runtime, requested, body, expected):
    _, load, *_ = runtime
    assert load().plan_turn(requested, body) == expected


@pytest.mark.asyncio
async def test_fresh_sustained_evidence_and_gesture_pause(runtime, monkeypatch):
    deps, load, state, status = runtime
    module = load()
    follower = module.StockFollower(deps)
    follower.running = True
    monkeypatch.setattr(module, "_read_doa", lambda: (0.0, True))
    monkeypatch.setattr(follower, "pose", lambda: (None, 0.0, 0.0, (0, 0)))
    queue = Mock()
    monkeypatch.setattr(follower, "queue", queue)
    for now in (10.0, 10.1, 10.2):
        await follower.step(state, now)
    queue.assert_not_called()
    status["breathing_active"] = False
    await follower.step(state, 10.3)
    assert follower.readings == []
    status["breathing_active"] = True
    for now in (10.4, 10.5, 10.6, 10.8):
        await follower.step(state, now)
    queue.assert_called_once_with((90.0, 55.0), 10.8)


@pytest.mark.asyncio
async def test_retained_heading_restored_through_queue_after_gesture(runtime, monkeypatch):
    deps, load, state, status = runtime
    module = load()
    follower = module.StockFollower(deps)
    follower.target = (100, 65)
    follower.holding = True
    queue = Mock()
    monkeypatch.setattr(follower, "queue", queue)
    status["breathing_active"] = False
    await follower.step(state, 10)
    queue.assert_not_called()
    status["breathing_active"] = True
    await follower.step(state, 11)
    queue.assert_called_once_with((100, 65), 11)
    assert not hasattr(deps.movement_manager, "set_voice_facing")


@pytest.mark.asyncio
async def test_robot_output_is_not_used_as_voice_evidence(runtime, monkeypatch):
    deps, load, state, _ = runtime
    module = load()
    follower = module.StockFollower(deps)
    reading = Mock(side_effect=AssertionError("Must not sample robot speech"))
    monkeypatch.setattr(module, "_read_doa", reading)
    state["speaking"] = True
    await follower.step(state, 10)
    reading.assert_not_called()


@pytest.mark.parametrize(
    "start,body,target,target_body",
    [(0, 0, 100, 65), (0, 0, -100, -65), (-160, -125, 175, 140), (175, 140, -155, -120)],
)
def test_full_yaw_path_keeps_body_and_relative_head_within_limits(runtime, start, body, target, target_body):
    _, load, *_ = runtime
    module = load()
    duration = module.turn_duration(start, body, target, target_body)
    move = module.FacingBreath(
        module.create_head_pose(yaw=start),
        (0, 0),
        math.radians(body),
        math.radians(target),
        math.radians(target_body),
        duration,
    )
    for moment in np.linspace(0, duration + 2, 201):
        pose, _, actual_body = move.evaluate(float(moment))
        heading = math.degrees(math.atan2(pose[1, 0], pose[0, 0]))
        assert abs(module.angular_delta(heading, math.degrees(actual_body))) <= 35.00001
        assert -125.00001 <= math.degrees(actual_body) <= 140.00001
    assert abs(module.angular_delta(heading, target)) < 0.00001
