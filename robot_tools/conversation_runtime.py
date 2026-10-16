"""External realtime relay: persistent quiet and app-owned voice-tool startup.

Run outside the external tools directory. Uses the app's supported local-backend setting and
the hosted HF realtime protocol; never imports, patches or writes conversation-app modules.
"""

import argparse
import asyncio
import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

LOG = logging.getLogger("reachy_tools.runtime")


def command_enabled(text: str) -> bool | None:
    """Recognise explicit control phrases without interpreting quoted/negated mentions."""
    import re

    normal = " ".join(re.sub(r"[^a-z\s]", "", text.lower()).split())
    normal = re.sub(r"^(?:(?:marvin|reachy|please|okay|ok|its fine|all right) )+", "", normal)
    normal = re.sub(r" please$", "", normal)
    if normal in {"shut up", "be quiet", "stop talking", "stop speaking", "stop answering", "quiet"}:
        return False
    if re.fullmatch(
        r"(?:you (?:can|may) (?:speak|talk)(?: again| now)?|(?:resume|start) (?:speaking|talking)(?: again)?)", normal
    ):
        return True
    return None


class State:
    """Durable speech state and bounded operational counters, with no conversation storage."""

    def __init__(self, path: Path):
        """Load the durable switch before accepting a realtime connection."""
        self.path = path
        self.lock = threading.RLock()
        self.enabled = True
        try:
            if path.exists():
                value = json.loads(path.read_text())["enabled"]
                if not isinstance(value, bool):
                    raise ValueError("enabled must be boolean")
                self.enabled = value
        except (OSError, ValueError, KeyError, TypeError):
            self.enabled = False
            LOG.error("Unreadable speech state; keeping output quiet")
        self.generation = 0
        self.voice_enabled = True
        self.voice_at = 0.0
        self.voice_worker = None
        self.audio_at = 0.0
        self.sessions = 0
        self.forwarded_audio = 0
        self.suppressed_audio = 0
        self.suppressed_tools = 0

    def set_enabled(self, enabled: bool):
        """Persist atomically and remain quiet if persistence fails."""
        with self.lock:
            self.enabled = False
            self.generation += 1
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".runtime.tmp")
            with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as output:
                json.dump({"enabled": enabled}, output)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(self.path)
            self.enabled = enabled
            LOG.info("speech enabled=%s generation=%s", enabled, self.generation)

    def status(self):
        """Return operational state without secrets or conversation content."""
        with self.lock:
            return {
                "enabled": self.enabled,
                "quiet": not self.enabled,
                "generation": self.generation,
                "voice_enabled": self.voice_enabled,
                "voice_running": time.monotonic() - self.voice_at < 3,
                "voice_worker": self.voice_worker,
                "speaking": time.monotonic() - self.audio_at < 0.8,
                "sessions": self.sessions,
                "forwarded_audio": self.forwarded_audio,
                "suppressed_audio": self.suppressed_audio,
                "suppressed_tools": self.suppressed_tools,
            }


class Gate:
    """One connection's response ownership; stopped replies cannot leak after resume."""

    def __init__(self, state: State):
        """Track response and startup ownership for one websocket session."""
        self.state = state
        self.active = None
        self.blocked = deque(maxlen=256)
        self.partial = {}
        self.skip_responses = 0
        self.local_calls = set()
        self.bootstrapped = False
        self.voice_available = False

    def block_active(self):
        """Prevent the active response from leaking after either speech transition."""
        if self.active and self.active not in self.blocked:
            self.blocked.append(self.active)

    def allow_output(self, event):
        """Decide whether the current response may produce audio or actions."""
        identity = event.get("response_id") or self.active
        return self.state.enabled and identity not in self.blocked


class Runtime:
    """Own relay connections, loopback controls and best-effort immediate playback interruption."""

    def __init__(self, state: State, config: dict[str, Any]):
        """Own only relay state, never robot motion or installed app modules."""
        self.state, self.config = state, config
        self.gates = set()
        self.loop = None

    async def interrupt(self):
        """Clear already-buffered playback through the stock app RPC."""
        try:
            async with connect(
                self.config.get("app_rpc", "ws://127.0.0.1:7860/rpc"), open_timeout=1, close_timeout=1
            ) as ws:
                await ws.send(
                    json.dumps({"jsonrpc": "2.0", "id": "quiet", "method": "conversation.interrupt", "params": {}})
                )
                async with asyncio.timeout(2):
                    while True:
                        result = json.loads(await ws.recv())
                        if result.get("id") == "quiet":
                            if "error" in result:
                                LOG.warning("Playback interrupt unavailable; relay output remains gated")
                            return
        except Exception as error:
            LOG.warning("Playback interrupt unavailable: %s; relay output remains gated", type(error).__name__)

    async def set_speech(self, enabled: bool):
        """Persist speech mode, gate existing responses and clear buffered playback."""
        # Block existing responses before either transition, including quiet->resume.
        for gate in tuple(self.gates):
            gate.block_active()
        self.state.set_enabled(enabled)
        await self.interrupt()
        return self.state.status()

    async def allocate(self, authorization: str | None):
        """Use the same hosted allocator and authentication as the stock app."""
        headers = {"User-Agent": "reachy-mini-conversation-app"}
        bearer = authorization if authorization and authorization != "Bearer DUMMY" else None
        if bearer is None:
            from huggingface_hub import get_token

            token = get_token()
            bearer = f"Bearer {token}" if token else None
        if bearer:
            headers["X-Reachy-Mini-Authorization"] = bearer
        async with httpx.AsyncClient(timeout=12) as client:
            result = await client.post(
                self.config["session_url"], headers=headers, json={"hardware_id": self.config["hardware_id"]}
            )
            result.raise_for_status()
            url = result.json().get("connect_url")
        if not isinstance(url, str) or not url.startswith("wss://"):
            raise ValueError("Allocator did not return a secure realtime endpoint")
        return url, bearer

    async def relay(self, downstream):
        """Relay one app session while enforcing persistent speech policy."""
        gate = Gate(self.state)
        self.gates.add(gate)
        self.state.sessions += 1
        session_number = self.state.sessions
        LOG.info("relay connected session=%s", session_number)
        try:
            url, authorization = await self.allocate(downstream.request.headers.get("Authorization"))
            headers = {"OpenAI-Beta": "realtime=v1"}
            if authorization:
                headers["Authorization"] = authorization
            async with connect(
                url, additional_headers=headers, max_size=16 * 1024 * 1024, open_timeout=20
            ) as upstream:

                async def client_events():
                    async for raw in downstream:
                        event = json.loads(raw)
                        kind = event.get("type")
                        if kind == "session.update":
                            gate.voice_available = any(
                                t.get("name") == "voice_look" for t in event.get("session", {}).get("tools", [])
                            )
                        if kind == "conversation.item.create":
                            item = event.get("item", {})
                            if item.get("type") == "function_call_output" and item.get("call_id") in gate.local_calls:
                                continue
                            if item.get("role") == "user":
                                text = " ".join(
                                    c.get("text", "") for c in item.get("content", []) if c.get("type") == "input_text"
                                )
                                control = command_enabled(text)
                                if control is not None:
                                    await self.set_speech(control)
                                    gate.skip_responses += 1
                                    continue
                                if not self.state.enabled:
                                    gate.skip_responses += 1
                                    continue
                        if kind == "response.create" and (not self.state.enabled or gate.skip_responses):
                            gate.skip_responses = max(0, gate.skip_responses - 1)
                            identity = "quiet-" + uuid.uuid4().hex
                            # Satisfy the app's serial response sender without starting model generation.
                            await downstream.send(
                                json.dumps(
                                    {
                                        "type": "response.created",
                                        "response": {
                                            "id": identity,
                                            "object": "realtime.response",
                                            "status": "in_progress",
                                            "output": [],
                                        },
                                    }
                                )
                            )
                            await downstream.send(
                                json.dumps(
                                    {
                                        "type": "response.done",
                                        "response": {
                                            "id": identity,
                                            "object": "realtime.response",
                                            "status": "completed",
                                            "output": [],
                                        },
                                    }
                                )
                            )
                            continue
                        await upstream.send(raw)

                async def server_events():
                    async for raw in upstream:
                        event = json.loads(raw)
                        kind = event.get("type", "")
                        if kind == "response.created":
                            gate.active = event["response"]["id"]
                            if not self.state.enabled:
                                gate.block_active()
                                await upstream.send(
                                    json.dumps({"type": "response.cancel", "response_id": gate.active})
                                )
                        if kind.startswith("conversation.item.input_audio_transcription."):
                            identity = event.get("item_id", "")
                            if kind.endswith(".delta"):
                                if len(gate.partial) > 32:
                                    gate.partial.clear()
                                text = gate.partial.get(identity, "") + event.get("delta", "")
                                gate.partial[identity] = text[-2000:]
                                control = command_enabled(text)
                                if control is False and self.state.enabled:
                                    await self.set_speech(False)
                            else:
                                gate.partial.pop(identity, None)
                                control = command_enabled(event.get("transcript", ""))
                                if control is not None and control != self.state.enabled:
                                    await self.set_speech(control)
                        gated = (
                            kind.startswith(("response.output_audio", "response.output_text"))
                            or kind == "response.function_call_arguments.done"
                        )
                        if gated and not gate.allow_output(event):
                            if kind == "response.output_audio.delta":
                                self.state.suppressed_audio += 1
                            if kind == "response.function_call_arguments.done":
                                self.state.suppressed_tools += 1
                            continue
                        if kind == "response.output_audio.delta":
                            self.state.audio_at = time.monotonic()
                            self.state.forwarded_audio += 1
                        await downstream.send(raw)
                        if kind == "response.done" and event.get("response", {}).get("id") == gate.active:
                            gate.active = None
                        if (
                            kind == "session.updated"
                            and not gate.bootstrapped
                            and gate.voice_available
                            and self.state.voice_enabled
                        ):
                            gate.bootstrapped = True
                            call = "runtime-voice-" + uuid.uuid4().hex
                            gate.local_calls.add(call)
                            await downstream.send(
                                json.dumps(
                                    {
                                        "type": "response.function_call_arguments.done",
                                        "response_id": call,
                                        "item_id": call,
                                        "output_index": 0,
                                        "call_id": call,
                                        "name": "voice_look",
                                        "arguments": '{"enabled":true}',
                                    }
                                )
                            )
                            LOG.info(
                                "voice follower requested through background-tool protocol session=%s", session_number
                            )

                tasks = [asyncio.create_task(client_events()), asyncio.create_task(server_events())]
                try:
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as error:
            LOG.error("relay session=%s ended: %s", session_number, type(error).__name__)
        finally:
            self.gates.discard(gate)
            await downstream.close()
            LOG.info("relay disconnected session=%s", session_number)

    def control_handler(self):
        """Build the bounded loopback-only HTTP control interface."""
        runtime = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, status, value):
                data = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path not in {"/state", "/health"}:
                    return self.respond(404, {"error": "not found"})
                self.respond(200, runtime.state.status())

            def do_POST(self):
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 4096:
                        raise ValueError("invalid body size")
                    payload = json.loads(self.rfile.read(size))
                    if self.path == "/speech":
                        if not isinstance(payload.get("enabled"), bool):
                            raise ValueError("enabled must be boolean")
                        future = asyncio.run_coroutine_threadsafe(runtime.set_speech(payload["enabled"]), runtime.loop)
                        return self.respond(200, future.result(timeout=5))
                    if self.path == "/voice":
                        if not isinstance(payload.get("enabled"), bool):
                            raise ValueError("enabled must be boolean")
                        runtime.state.voice_enabled = payload["enabled"]
                    elif self.path == "/heartbeat":
                        runtime.state.voice_at = time.monotonic() if payload.get("running") else 0.0
                        runtime.state.voice_worker = payload.get("worker")
                    else:
                        return self.respond(404, {"error": "not found"})
                    self.respond(200, runtime.state.status())
                except Exception as error:
                    self.respond(503, {"error": type(error).__name__})

        return Handler

    async def run(self):
        """Serve loopback websocket and HTTP controls until supervisor shutdown."""
        self.loop = asyncio.get_running_loop()
        http = ThreadingHTTPServer(("127.0.0.1", self.config.get("control_port", 8767)), self.control_handler())
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            async with serve(self.relay, "127.0.0.1", self.config.get("relay_port", 8766), max_size=16 * 1024 * 1024):
                await asyncio.Event().wait()
        finally:
            http.shutdown()


def main():
    """Start the independently supervised relay from external configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = json.loads(args.config.read_text())
    asyncio.run(Runtime(State(Path(config["speech_state"]).expanduser()), config).run())


if __name__ == "__main__":
    main()
