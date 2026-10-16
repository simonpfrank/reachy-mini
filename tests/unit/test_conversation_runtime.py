"""Exercise the external relay's real websocket path without a robot or hosted provider."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from robot_tools.conversation_runtime import Gate, Runtime, State, command_enabled


@pytest.mark.parametrize(
    "text,expected",
    [
        ("shut up", False),
        ("Marvin, please be quiet!", False),
        ("you can speak again", True),
        ("don't shut up", None),
        ("what does shut up mean", None),
        ("you can speak again when I say so", None),
    ],
)
def test_explicit_control_phrases(text, expected):
    assert command_enabled(text) is expected


def test_quiet_survives_service_restart_and_invalid_state_fails_quiet(tmp_path):
    path = tmp_path / "speech.json"
    state = State(path)
    state.set_enabled(False)
    assert State(path).status()["quiet"]
    state.set_enabled(True)
    assert not State(path).status()["quiet"]
    path.write_text("invalid")
    assert State(path).status()["quiet"]


def test_stopped_response_stays_blocked_after_resume(tmp_path):
    state = State(tmp_path / "speech.json")
    gate = Gate(state)
    gate.active = "old"
    gate.block_active()
    state.set_enabled(False)
    state.set_enabled(True)
    assert not gate.allow_output({"response_id": "old"})
    assert gate.allow_output({"response_id": "new"})


@pytest.mark.asyncio
async def test_real_relay_gates_typed_voice_audio_and_tools_but_keeps_microphone_live(tmp_path, monkeypatch):
    received = asyncio.Queue()
    send_to_client = asyncio.Queue()

    async def backend(ws):
        async def read():
            async for raw in ws:
                event = json.loads(raw)
                await received.put(event)
                if event["type"] == "session.update":
                    await ws.send(json.dumps({"type": "session.updated", "session": {}}))

        async def write():
            while True:
                await ws.send(json.dumps(await send_to_client.get()))

        tasks = [asyncio.create_task(read()), asyncio.create_task(write())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async with serve(backend, "127.0.0.1", 0) as provider:
        url = f"ws://127.0.0.1:{provider.sockets[0].getsockname()[1]}/realtime"
        runtime = Runtime(State(tmp_path / "speech.json"), {})
        monkeypatch.setattr(runtime, "allocate", AsyncMock(return_value=(url, None)))
        monkeypatch.setattr(runtime, "interrupt", AsyncMock())
        async with serve(runtime.relay, "127.0.0.1", 0) as relay:
            target = f"ws://127.0.0.1:{relay.sockets[0].getsockname()[1]}/realtime"
            async with connect(target) as app:

                async def send(event):
                    await app.send(json.dumps(event))

                async def receive():
                    return json.loads(await asyncio.wait_for(app.recv(), 2))

                async def typed(text):
                    await send(
                        {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": text}],
                            },
                        }
                    )
                    await send({"type": "response.create"})
                    assert (await receive())["type"] == "response.created"
                    assert (await receive())["type"] == "response.done"

                await send({"type": "session.update", "session": {"tools": [{"name": "voice_look"}]}})
                assert (await receive())["type"] == "session.updated"
                startup = await receive()
                assert startup["name"] == "voice_look"
                assert json.loads(startup["arguments"]) == {"enabled": True}
                assert (await received.get())["type"] == "session.update"
                await typed("shut up")
                assert runtime.state.status()["quiet"]
                await typed("dance")
                # Raw microphone frames still reach STT; no microphone mute call is made.
                await send({"type": "input_audio_buffer.append", "audio": "AA=="})
                assert (await asyncio.wait_for(received.get(), 2))["type"] == "input_audio_buffer.append"
                await send_to_client.put({"type": "response.created", "response": {"id": "old"}})
                assert (await receive())["type"] == "response.created"
                assert (await received.get())["type"] == "response.cancel"
                await send_to_client.put(
                    {"type": "response.output_audio.delta", "response_id": "old", "delta": "AA=="}
                )
                await send_to_client.put(
                    {"type": "response.function_call_arguments.done", "response_id": "old", "name": "dance"}
                )
                await typed("you can speak again")
                # Process order on separate streams can interleave; drain with an explicit fresh marker.
                await send_to_client.put(
                    {"type": "response.output_audio.delta", "response_id": "old", "delta": "AA=="}
                )
                await send_to_client.put({"type": "response.created", "response": {"id": "fresh"}})
                assert (await receive())["response"]["id"] == "fresh"
                await send_to_client.put(
                    {"type": "response.output_audio.delta", "response_id": "fresh", "delta": "AA=="}
                )
                assert (await receive())["response_id"] == "fresh"
                assert runtime.state.suppressed_audio == 2
                assert runtime.state.suppressed_tools == 1
                # A spoken command is recognised before dispatching the model's next tool/output.
                await send_to_client.put(
                    {
                        "type": "conversation.item.input_audio_transcription.completed",
                        "item_id": "voice",
                        "transcript": "shut up",
                    }
                )
                assert (await receive())["transcript"] == "shut up"
                assert runtime.state.status()["quiet"]
                assert runtime.interrupt.await_count >= 3
