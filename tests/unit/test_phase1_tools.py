"""Exercise persistent quiet/resume and shared location without robot hardware."""

import importlib.util
import io
import json
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from robot_tools.install_phase1 import patch_source
from robot_tools.install_voice_look_lifecycle import patch_main

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
@pytest.mark.parametrize("port", [None, "8787"])
async def test_speech_control_can_use_development_service_without_touching_live_service(modules, monkeypatch, port):
    if port is None:
        monkeypatch.delenv("REACHY_TOOLS_CONTROL_PORT", raising=False)
    else:
        monkeypatch.setenv("REACHY_TOOLS_CONTROL_PORT", port)
    seen = []

    def respond(request, timeout):
        seen.append(request.full_url)
        return io.BytesIO(b'{"enabled": false}')

    monkeypatch.setattr(modules.speech_control.urllib.request, "urlopen", respond)
    assert await modules.speech_control.SpeechControl()(None) == {"enabled": False}
    assert seen == [f"http://127.0.0.1:{port or '8767'}/state"]


@pytest.fixture
def modules(monkeypatch):
    core = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
    core.Tool = type("Tool", (), {})
    core.ToolDependencies = types.SimpleNamespace
    monkeypatch.setitem(sys.modules, core.__name__, core)
    loaded = {}
    for name in ("speech_control", "location"):
        spec = importlib.util.spec_from_file_location(f"_phase1_{name}", ROOT / "robot_tools" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded[name] = module
    return types.SimpleNamespace(**loaded)


@pytest.fixture
def state(modules, tmp_path):
    deps = types.SimpleNamespace(movement_manager=types.SimpleNamespace())
    stream = Mock()
    stream.handler.connection = types.SimpleNamespace(
        response=types.SimpleNamespace(cancel=AsyncMock()),
        conversation=types.SimpleNamespace(item=types.SimpleNamespace(create=AsyncMock())),
    )
    owner = modules.speech_control.SpeechState(deps, stream, tmp_path / "speech.json")
    return owner, stream


@pytest.mark.parametrize("text,expected", [
    ("Shut up!", False), ("Marvin, please be quiet.", False), ("stop answering", False),
    ("You can speak again", True), ("Okay, resume talking please", True),
    ("don't shut up", None), ("what does shut up mean", None),
    ("you can speak again when I say so", None), ("keep quiet about that", None),
])
def test_only_explicit_control_commands_switch_mode(modules, text, expected):
    assert modules.speech_control.command_enabled(text) is expected


@pytest.mark.asyncio
async def test_quiet_flushes_audio_and_survives_app_restart_without_muting_microphone(modules, state):
    owner, stream = state
    assert await owner.handle_text("shut up")
    assert owner.quiet
    stream.clear_audio_queue.assert_called_once()
    assert json.loads(owner.path.read_text()) == {"enabled": False}
    restarted = modules.speech_control.SpeechState(owner.deps, stream, owner.path)
    assert restarted.quiet
    assert await restarted.handle_text("tell me the weather")
    assert restarted.quiet
    assert await restarted.handle_text("you can speak again")
    assert not restarted.quiet
    assert json.loads(owner.path.read_text()) == {"enabled": True}


@pytest.mark.asyncio
async def test_unreadable_state_fails_quiet_and_failed_write_cannot_unmute(modules, state, monkeypatch):
    owner, stream = state
    owner.path.write_text("invalid")
    restarted = modules.speech_control.SpeechState(owner.deps, stream, owner.path)
    assert restarted.quiet and restarted.persistence_error
    monkeypatch.setattr(restarted, "_save", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        await restarted.set_enabled(True)
    assert restarted.quiet


@pytest.mark.asyncio
async def test_quiet_blocks_current_and_late_audio_even_after_resume(state):
    owner, stream = state
    handler = stream.handler
    event = types.SimpleNamespace
    assert not await owner.on_event(event(type="response.created", response=event(id="old")), handler)
    await owner.set_enabled(False)
    assert await owner.on_event(event(type="response.output_audio.delta", response_id="old"), handler)
    await owner.set_enabled(True)
    assert await owner.on_event(event(type="response.output_audio.delta", response_id="old"), handler)
    assert not await owner.on_event(event(type="response.done"), handler)
    assert not await owner.on_event(event(type="response.created", response=event(id="new")), handler)
    assert not await owner.on_event(event(type="response.output_audio.delta", response_id="new"), handler)
    assert owner.last_audio_at > 0


@pytest.mark.asyncio
async def test_spoken_controls_keep_transcription_and_response_cleanup_alive(state):
    owner, stream = state
    event = types.SimpleNamespace
    kind = "conversation.item.input_audio_transcription.completed"
    assert not await owner.on_event(event(type=kind, transcript="shut up"), stream.handler)
    assert owner.quiet
    stream.handler.connection.response.cancel.assert_awaited_once()
    assert not await owner.on_event(event(type="response.done"), stream.handler)
    assert not await owner.on_event(event(type=kind, transcript="you can speak again"), stream.handler)
    assert not owner.quiet


@pytest.mark.asyncio
async def test_quiet_model_tool_call_is_answered_without_execution(state):
    owner, stream = state
    await owner.set_enabled(False)
    event = types.SimpleNamespace(type="response.function_call_arguments.done", call_id="call1")
    assert await owner.on_event(event, stream.handler)
    item = stream.handler.connection.conversation.item.create.call_args.kwargs["item"]
    assert item["call_id"] == "call1"
    assert json.loads(item["output"]) == {"status": "quiet", "executed": False}


@pytest.mark.asyncio
async def test_async_audio_flush_in_app_1_1_is_awaited_before_resume(state):
    owner, stream = state

    async def flush():
        assert owner.quiet

    stream.clear_audio_queue = AsyncMock(side_effect=flush)
    await owner.set_enabled(False)
    await owner.set_enabled(True)
    assert stream.clear_audio_queue.await_count == 2
    assert not owner.quiet


def test_location_default_is_provisional_and_configured_override_is_shared(modules, tmp_path):
    path = tmp_path / "location.json"
    default = modules.location.location_payload(path)
    assert default["place"] == "Cobham" and default["provisional"]
    path.write_text(json.dumps({"place": "London", "region": "Greater London", "latitude": 51.5, "longitude": -0.1}))
    configured = modules.location.location_payload(path)
    assert configured["place"] == "London" and not configured["provisional"]
    assert configured["latitude"] == 51.5 and configured["source"] == "configured_file"


@pytest.mark.parametrize("config", [
    {"latitude": 51.5}, {"latitude": 91, "longitude": 0},
    {"latitude": True, "longitude": 0}, {"place": ""},
])
def test_bad_location_is_rejected_instead_of_silently_guessed(modules, tmp_path, config):
    path = tmp_path / "location.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError):
        modules.location.location_payload(path)


def test_phase1_startup_composes_with_voice_lifecycle_and_is_idempotent():
    source = '''def run():
    from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
    try:
        stream_manager.launch()
    finally:
        if own_ui_server is not None:
            pass
'''
    patched = patch_source("main.py", patch_main(source))
    assert patched.index("speech_tool.start") < patched.index("stream_manager.launch")
    assert 'get_tools().get("speech_control")' not in patched
    assert 'speech_module.SpeechControl()' in patched
    assert patch_source("main.py", patched) == patched
    assert patch_main(patched) == patched
    with pytest.raises(ValueError, match="Partial"):
        patch_source("main.py", patched.replace("speech_tool.start", "speech_tool.broken"))
    with pytest.raises(ValueError, match="Unexpected"):
        patch_source("main.py", "pass\n")
