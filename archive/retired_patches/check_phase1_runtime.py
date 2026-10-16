"""Historical patched-class regression experiment, not a stock-app compatibility check.

Transforms copies in a temporary directory only; it does not edit the selected installed app.
Passing this experiment cannot establish update survival or current robot functionality.
Patch deployment is retired. Keep outside the external tools directory.
"""

# ruff: noqa: S101

import asyncio
import importlib.util
import json
import math
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import numpy as np
from archive.retired_patches.install_phase1 import PATCHES, patch_source


def load(name, path):
    """Load real staged classes, without running an app entry point."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


async def check(app_dir):
    """Sample turns and simulate gestures, response queues and the final playback gate."""
    here = Path(__file__).resolve().parents[2] / "robot_tools"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name in PATCHES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            source = patch_source(name, (app_dir / name).read_text())
            assert patch_source(name, source) == source
            path.write_text(source)
        moves = load("reachy_mini_conversation_app.moves", root / "moves.py")
        voice = load("_phase1_voice", here / "voice_look.py")
        speech = load("_phase1_speech", here / "speech_control.py")
        location = load("_phase1_location", here / "location.py")
        core = load("_phase1_core", root / "tools/core_tools.py")
        realtime = load("_phase1_realtime", root / "huggingface_realtime.py")
        console = load("_phase1_console", root / "console.py")
        robot = Mock()
        manager = moves.MovementManager(robot)
        deps = core.ToolDependencies(robot, manager)
        samples = 0
        for start, body, requested in [(0, 0, 100), (0, 0, -100), (-160, -125, 180), (175, 140, -155)]:
            target, target_body = voice.plan_turn(requested, body)
            duration = voice.turn_duration(start, body, target, target_body)
            move = voice.FacingBreath(
                voice.create_head_pose(yaw=start), (0, 0), math.radians(body),
                math.radians(target), math.radians(target_body), duration,
            )
            for moment in np.linspace(0, duration + 2, 201):
                head, _, body_yaw = move.evaluate(float(moment))
                heading = math.degrees(math.atan2(head[1, 0], head[0, 0]))
                assert abs(voice.angular_delta(heading, math.degrees(body_yaw))) <= 35.00001
                assert -125.00001 <= math.degrees(body_yaw) <= 140.00001
                samples += 1
            assert abs(voice.angular_delta(heading, target)) < 0.00001

        # A finite gesture finishes, then the actual manager must create speaker-facing idle again.
        robot.get_current_head_pose.return_value = voice.create_head_pose(yaw=20)
        robot.get_current_joint_positions.return_value = ([math.radians(10)], (0, 0))
        owner = voice._Controller(deps)
        manager._voice_look_idle_factory = owner._idle_move
        manager.set_voice_facing(math.radians(100), math.radians(65))
        manager._poll_signals(manager._now())
        manager.state.current_move = SimpleNamespace(duration=0.1)
        manager.state.move_start_time = manager._now() - 1
        manager.state.last_activity_time = manager._now() - 1
        manager._manage_move_queue(manager._now())
        manager._manage_breathing(manager._now())
        assert isinstance(manager.move_queue[0], voice.FacingBreath)
        restored = manager.move_queue[0]
        assert math.isclose(restored._heading, math.radians(100))
        manager._handle_command("set_speaking", True, manager._now())
        assert manager.get_status()["is_speaking"] and not manager._head_tracking
        robot.set_target.assert_not_called()

        handler = realtime.HuggingFaceRealtimeHandler.__new__(realtime.HuggingFaceRealtimeHandler)
        handler.deps = deps
        handler.connection = SimpleNamespace(
            response=SimpleNamespace(create=AsyncMock(), cancel=AsyncMock()),
            conversation=SimpleNamespace(item=SimpleNamespace(create=AsyncMock())),
        )
        handler._pending_responses = asyncio.Queue()
        handler.playback_epoch = 0
        handler.playback_frame_epochs = {}
        handler.paced_playback = False
        handler._mark_activity = Mock()
        handler._emit_transcript = Mock()
        stream = Mock()
        stream.handler = handler
        state = speech.SpeechState(deps, stream, root / "speech.json")
        manager._speech_control = state
        await handler._safe_response_create()
        assert handler._pending_responses.qsize() == 1
        await handler.say("shut up")
        assert state.quiet and handler._pending_responses.empty()
        await handler.say("this should not be sent to the model")
        handler.connection.conversation.item.create.assert_not_awaited()
        result = await core._dispatch_tool_call("move_head", {}, deps)
        assert result == {"status": "quiet", "executed": False}
        await handler._safe_response_create()
        assert handler._pending_responses.empty()

        # Exercise actual console playback, not only the upstream event filter.
        playback = console.LocalStream.__new__(console.LocalStream)
        playback.handler = handler
        playback._robot = robot
        playback._stop_event = asyncio.Event()

        async def emit():
            playback._stop_event.set()
            return 24000, np.zeros(240, dtype=np.int16)

        handler.emit = emit
        await playback.play_loop()
        robot.media.push_audio_sample.assert_not_called()
        assert speech.SpeechState(deps, stream, root / "speech.json").quiet
        await handler.say("you can speak again")
        assert not state.quiet
        await handler.say("ordinary instruction")
        handler.connection.conversation.item.create.assert_awaited_once()
        assert handler._pending_responses.qsize() == 1
        assert location.location_payload(root / "no-location.json")["provisional"]
        print(json.dumps({"ok": True, "turn_samples": samples, "checks": [
            "patch_idempotence", "physical_yaw_limits", "heading_after_gesture", "speech_without_face_tracking",
            "quiet_stops_pending_responses", "quiet_blocks_tools", "final_playback_gate", "restart_persistence",
            "explicit_resume", "ordinary_text_turn", "shared_location",
        ]}))


if __name__ == "__main__":
    asyncio.run(check(Path(sys.argv[1])))
