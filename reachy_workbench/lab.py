"""Run the real relay against explicit offline fake peers, with no hardware or cloud."""

import asyncio
import json
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from robot_tools.conversation_runtime import Runtime, State


class LocalRuntime(Runtime):
    """Override only provider allocation; all relay policy/transport is production code."""

    async def allocate(self, authorization: str | None) -> tuple[str, None]:
        """Connect to the lab provider without reading a token or making a cloud request."""
        return self.config["lab_provider"], None


class Lab:
    """Own isolated peers, state and event observations for one development session."""

    def __init__(self, state_path: Path):
        """Keep local state separate from robot configuration and remember visible observations."""
        self.state_path = state_path
        self.stack = AsyncExitStack()
        self.audio_markers = 0
        self.actions = 0
        self.bootstrap_requests = 0
        self.interrupts = 0
        self.sequence = 0
        self.provider: Any = None
        self.app: Any = None
        self.runtime: LocalRuntime | None = None
        self.mic_seen = asyncio.Event()

    async def __aenter__(self) -> "Lab":
        """Start the lab's loopback servers on available ports."""
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Close sockets and owned tasks without leaving background processes."""
        await self.stack.aclose()

    async def rpc_peer(self, ws: Any) -> None:
        """Fake the stock interrupt acknowledgement; never manipulate real audio."""
        async for raw in ws:
            request = json.loads(raw)
            if request.get("method") == "conversation.interrupt":
                self.interrupts += 1
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": {"ok": True}}))

    async def provider_peer(self, ws: Any) -> None:
        """Emit deterministic protocol events instead of invoking STT, an LLM or TTS."""
        self.provider = ws
        pending = ""
        async for raw in ws:
            event = json.loads(raw)
            kind = event.get("type")
            if kind == "session.update":
                await ws.send(json.dumps({"type": "session.updated", "session": {}}))
            elif kind == "conversation.item.create":
                pending = " ".join(part.get("text", "") for part in event["item"].get("content", []))
            elif kind == "input_audio_buffer.append":
                self.mic_seen.set()
            elif kind == "response.create":
                self.sequence += 1
                identity = f"lab-response-{self.sequence}"
                events = [{"type": "response.created", "response": {"id": identity}}]
                if pending == "dance":
                    events.append(
                        {
                            "type": "response.function_call_arguments.done",
                            "response_id": identity,
                            "name": "dance",
                            "arguments": "{}",
                        }
                    )
                else:
                    events.extend(
                        [
                            {"type": "response.output_audio.delta", "response_id": identity, "delta": "AA=="},
                            {
                                "type": "response.output_audio_transcript.done",
                                "response_id": identity,
                                "transcript": f"Simulated reply: {pending}",
                            },
                        ]
                    )
                events.append({"type": "response.done", "response": {"id": identity}})
                for response in events:
                    await ws.send(json.dumps(response))

    async def start(self) -> None:
        """Start fresh transport peers using the existing isolated speech-state file."""
        rpc = await self.stack.enter_async_context(serve(self.rpc_peer, "127.0.0.1", 0))
        provider = await self.stack.enter_async_context(serve(self.provider_peer, "127.0.0.1", 0))
        self.runtime = LocalRuntime(
            State(self.state_path),
            {
                "app_rpc": f"ws://127.0.0.1:{rpc.sockets[0].getsockname()[1]}/rpc",
                "lab_provider": f"ws://127.0.0.1:{provider.sockets[0].getsockname()[1]}/realtime",
            },
        )
        relay = await self.stack.enter_async_context(serve(self.runtime.relay, "127.0.0.1", 0))
        self.app = await self.stack.enter_async_context(
            connect(f"ws://127.0.0.1:{relay.sockets[0].getsockname()[1]}/realtime")
        )
        await self.app.send(json.dumps({"type": "session.update", "session": {"tools": [{"name": "voice_look"}]}}))
        await self.receive_until("session.updated")

    async def receive_until(self, kind: str) -> dict[str, Any]:
        """Observe the actual forwarded events, with a bounded wait and explicit counters."""
        async with asyncio.timeout(3):
            while True:
                event = json.loads(await self.app.recv())
                name = event.get("type")
                if name == "response.output_audio.delta":
                    self.audio_markers += 1
                if name == "response.function_call_arguments.done":
                    if event.get("name") == "voice_look":
                        self.bootstrap_requests += 1
                    else:
                        self.actions += 1
                if name == kind:
                    return event

    async def turn(self, text: str) -> dict[str, Any]:
        """Send a typed user turn through the real relay; report observed transport effects."""
        before_audio, before_actions = self.audio_markers, self.actions
        await self.app.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]},
                }
            )
        )
        await self.app.send(json.dumps({"type": "response.create"}))
        await self.receive_until("response.done")
        return {
            "quiet": self.runtime.state.status()["quiet"],
            "audio_markers": self.audio_markers - before_audio,
            "actions": self.actions - before_actions,
        }

    async def transcript(self, text: str) -> dict[str, Any]:
        """Inject an explicitly simulated STT completion through the provider websocket."""
        await self.provider.send(
            json.dumps(
                {
                    "type": "conversation.item.input_audio_transcription.completed",
                    "item_id": f"lab-speech-{self.sequence}",
                    "transcript": text,
                }
            )
        )
        await self.receive_until("conversation.item.input_audio_transcription.completed")
        return self.runtime.state.status()

    async def microphone(self) -> None:
        """Verify an input-audio marker reaches the fake STT provider while quiet."""
        self.mic_seen.clear()
        await self.app.send(json.dumps({"type": "input_audio_buffer.append", "audio": "AA=="}))
        await asyncio.wait_for(self.mic_seen.wait(), timeout=3)

    async def restart(self) -> None:
        """Restart all lab peers and reload persisted state, without changing a robot."""
        await self.stack.aclose()
        self.stack = AsyncExitStack()
        await self.start()


async def demo(state_path: Path, output=print) -> list[str]:
    """Run a visible, repeatable offline scenario; raise rather than report false success."""
    checks: list[str] = []

    def passed(message: str) -> None:
        checks.append(message)
        output(f"PASS {message}")

    async with Lab(state_path) as lab:
        await lab.transcript("you can speak again")
        normal = await lab.turn("hello")
        if normal["audio_markers"] != 1:
            raise RuntimeError("Normal reply did not traverse the relay")
        passed("normal reply crosses the real relay")
        quiet = await lab.turn("shut up")
        if not quiet["quiet"] or quiet["audio_markers"] or quiet["actions"]:
            raise RuntimeError("Quiet command emitted output/actions or failed to persist")
        passed("quiet command produces no output or action")
        blocked = await lab.turn("dance")
        if blocked["audio_markers"] or blocked["actions"]:
            raise RuntimeError("An ordinary request executed while quiet")
        passed("ordinary request cannot dispatch an action while quiet")
        await lab.microphone()
        passed("microphone transport remains open while quiet")
        await lab.restart()
        if not lab.runtime.state.status()["quiet"]:
            raise RuntimeError("Quiet state was lost on runtime restart")
        passed("quiet survives a complete local runtime restart")
        await lab.transcript("you can speak again")
        resumed = await lab.turn("hello again")
        if resumed["quiet"] or resumed["audio_markers"] != 1:
            raise RuntimeError("Explicit resume failed")
        passed("simulated spoken resume restores subsequent output")
    return checks
