"""Turning toward voices: immediate replies, worker lifetime, safe poses and queue arbitration."""

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
from reachy_mini.utils import create_head_pose

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
async def test_call_replies_at_once_and_one_worker_survives_reload(runtime):
    deps, load, *_ = runtime
    module = load()
    result = await asyncio.wait_for(module.VoiceLook()(deps), timeout=1)  # no arguments means on
    assert result == {"enabled": True, "turning_to_voices": True}
    owner = deps.movement_manager._stock_voice_follower
    first = owner.task
    try:
        await asyncio.sleep(0.01)
        assert owner.running and not first.done()
        again = await module.VoiceLook()(deps, enabled=True)  # same code: the running worker is kept
        assert again == {"enabled": True, "turning_to_voices": True}
        assert deps.movement_manager._stock_voice_follower.task is first
        reloaded = load().VoiceLook()  # tool reload: the old worker ends before a new one starts
        assert await reloaded(deps, enabled=True) == {"enabled": True, "turning_to_voices": True}
        current = deps.movement_manager._stock_voice_follower
        assert first.done() and current is not owner and current.running
        assert await reloaded(deps, enabled=False) == {"enabled": False, "turning_to_voices": False}
        assert current.task.done() and not current.running
    finally:
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)


@pytest.mark.asyncio
async def test_worker_left_by_an_older_version_is_stopped_and_replaced(runtime):
    deps, load, *_ = runtime

    async def old_loop():
        while old.running:
            await asyncio.sleep(0.001)

    old = types.SimpleNamespace(running=True)  # the previous version had no start()
    old.task = asyncio.create_task(old_loop())
    deps.movement_manager._stock_voice_follower = old
    assert await load().VoiceLook()(deps) == {"enabled": True, "turning_to_voices": True}
    assert old.task.done() and not old.running
    current = deps.movement_manager._stock_voice_follower
    assert current is not old and current.running
    await load().VoiceLook()(deps, enabled=False)


@pytest.mark.asyncio
async def test_app_shutdown_cancellation_ends_worker_and_it_can_restart(runtime):
    deps, load, *_ = runtime
    tool = load().VoiceLook()
    await tool(deps)
    owner = deps.movement_manager._stock_voice_follower
    cancelled = owner.task
    cancelled.cancel()  # before the worker has run at all
    await asyncio.gather(cancelled, return_exceptions=True)
    await tool(deps)
    assert owner.running and owner.task is not cancelled and not owner.task.done()
    await tool(deps, enabled=False)


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
    await deps.movement_manager._stock_voice_follower.task
    assert seen == [True]


def test_schema_lets_the_model_call_with_no_arguments(runtime):
    _, load, *_ = runtime
    tool = load().VoiceLook
    assert tool.parameters_schema["required"] == []
    assert tool.parameters_schema["properties"]["enabled"]["description"]


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
    queue.assert_called_once_with((90.0, 55.0), 10.8, "voice", 90.0, 4)


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
    queue.assert_called_once_with((100, 65), 11, "restore")
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
        create_head_pose(yaw=start),
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



@pytest.mark.parametrize(
    "start,body,target,target_body",
    [(0, 0, 100, 65), (-75, -110, -20, -55), (-90, -125, -140, -125), (-60, -95, 175, 140)],
)
def test_turns_never_exceed_the_peak_speed_limits(runtime, start, body, target, target_body):
    _, load, *_ = runtime
    module = load()
    duration = module.turn_duration(start, body, target, target_body)
    move = module.FacingBreath(
        create_head_pose(yaw=start),
        (0, 0),
        math.radians(body),
        math.radians(target),
        math.radians(target_body),
        duration,
    )
    moments = np.linspace(0, duration, 400)
    samples = [move.evaluate(float(t)) for t in moments]
    bodies = np.degrees([sample[2] for sample in samples])
    heads = np.degrees(np.unwrap([math.atan2(s[0][1, 0], s[0][0, 0]) for s in samples]))
    step = moments[1] - moments[0]
    # the limits (head 40, body 35 deg/s) are in reachy_lib.motion
    assert np.abs(np.diff(bodies)).max() / step <= 35 * 1.01
    assert np.abs(np.diff(heads)).max() / step <= 40 * 1.01

@pytest.mark.asyncio
async def test_on_off_and_turns_are_logged_with_their_reasons(runtime, caplog):
    deps, load, *_ = runtime
    module = load()
    caplog.set_level("INFO")
    tool = module.VoiceLook()
    await tool(deps)
    await tool(deps)
    await tool(deps, enabled=False)
    await tool(deps, enabled=False)
    follower = deps.movement_manager._stock_voice_follower
    follower.pose = lambda: (create_head_pose(), 10.0, 0.0, (0, 0))
    deps.movement_manager.get_status = lambda: {}
    follower.queue((80.0, 45.0), 1.0, "voice", 80.0, 5)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("VOICE_LOOK")]
    worker = follower.worker
    assert lines[0] == f"VOICE_LOOK request worker={worker} enabled=true result=started"
    assert f"VOICE_LOOK on worker={worker}" in lines
    assert f"VOICE_LOOK request worker={worker} enabled=true result=already_on" in lines
    assert f"VOICE_LOOK off worker={worker} reason=stopped" in lines
    assert f"VOICE_LOOK request worker={worker} enabled=false result=stopped" in lines
    assert f"VOICE_LOOK request worker={worker} enabled=false result=already_off" in lines
    assert lines[-1] == (
        f"VOICE_LOOK turn worker={worker} reason=voice heard=+80.0 readings=5 from_head=+10.0 from_body=+0.0 "
        "head=+80.0 body=+45.0"
    )
