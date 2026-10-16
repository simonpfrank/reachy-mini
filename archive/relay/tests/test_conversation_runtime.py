"""Exercise the external relay's real websocket path without a robot or hosted provider."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from robot_tools.conversation_runtime import Runtime, State


def test_quiet_survives_service_restart_and_invalid_state_fails_quiet(tmp_path):
    path = tmp_path / "speech.json"
    state = State(path)
    state.set_enabled(False)
    assert State(path).status()["quiet"]
    state.set_enabled(True)
    assert not State(path).status()["quiet"]
    path.write_text("invalid")
    assert State(path).status()["quiet"]


@pytest.mark.asyncio
async def test_mute_switch_preserves_volume_and_never_interrupts(tmp_path, monkeypatch):
    runtime = Runtime(State(tmp_path / "speech.json"), {})
    process = AsyncMock()
    process.returncode = 0
    process.communicate.side_effect = [(b"Playback 45 [75%] [off]", b""), (b"Playback 45 [75%] [on]", b"")]
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    await runtime.set_speech(False)
    assert State(runtime.state.path).status()["speaker_muted"]
    await runtime.set_speech(True)
    assert not runtime.state.status()["speaker_muted"]
    assert spawn.call_args_list[0].args == ("amixer", "-c", "Audio", "sset", "PCM,0", "mute")
    assert spawn.call_args_list[1].args == ("amixer", "-c", "Audio", "sset", "PCM,0", "unmute")


@pytest.mark.asyncio
async def test_failed_mute_is_reported_without_saving_success(tmp_path, monkeypatch):
    runtime = Runtime(State(tmp_path / "speech.json"), {})
    monkeypatch.setattr(runtime, "apply_speaker", AsyncMock(side_effect=RuntimeError("device failed")))
    with pytest.raises(RuntimeError):
        await runtime.set_speech(False)
    assert runtime.state.enabled
    assert not runtime.state.path.exists()


@pytest.mark.asyncio
async def test_muted_relay_keeps_replies_tools_transcripts_and_microphone_live(tmp_path, monkeypatch):
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
        monkeypatch.setattr(runtime, "apply_speaker", AsyncMock())
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
                    assert (await asyncio.wait_for(received.get(), 2))["item"]["content"][0]["text"] == text
                    assert (await asyncio.wait_for(received.get(), 2))["type"] == "response.create"

                await send({"type": "session.update", "session": {"tools": [{"name": "voice_look"}]}})
                assert (await receive())["type"] == "session.updated"
                startup = await receive()
                assert startup["name"] == "voice_look"
                assert json.loads(startup["arguments"]) == {"enabled": True}
                assert (await received.get())["type"] == "session.update"
                # Natural commands reach the model; only the tool controls the speaker.
                await typed("Please stop making noise for a while")
                assert runtime.state.enabled
                await runtime.set_speech(False)
                assert runtime.state.status()["quiet"]
                await typed("dance")
                # Raw microphone frames still reach STT; no microphone mute call is made.
                await send({"type": "input_audio_buffer.append", "audio": "AA=="})
                assert (await asyncio.wait_for(received.get(), 2))["type"] == "input_audio_buffer.append"
                await send_to_client.put({"type": "response.created", "response": {"id": "old"}})
                assert (await receive())["type"] == "response.created"
                await send_to_client.put(
                    {"type": "response.output_audio.delta", "response_id": "old", "delta": "AA=="}
                )
                await send_to_client.put(
                    {"type": "response.function_call_arguments.done", "response_id": "old", "name": "dance"}
                )
                assert (await receive())["type"] == "response.output_audio.delta"
                assert (await receive())["name"] == "dance"
                await send_to_client.put({"type": "response.output_audio_transcript.done", "transcript": "Done"})
                assert (await receive())["transcript"] == "Done"
                await typed("I would like to hear you now")
                assert not runtime.state.enabled
                await runtime.set_speech(True)
                assert runtime.state.enabled
                assert runtime.state.suppressed_audio == 0
                assert runtime.state.suppressed_tools == 0
                # Spoken phrases are forwarded intact, never interpreted by the relay.
                await send_to_client.put(
                    {
                        "type": "conversation.item.input_audio_transcription.completed",
                        "item_id": "voice",
                        "transcript": "shut up",
                    }
                )
                assert (await receive())["transcript"] == "shut up"
                assert runtime.state.enabled
                assert runtime.apply_speaker.await_count == 2
