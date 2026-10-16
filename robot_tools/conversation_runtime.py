"""External realtime relay: persistent speaker mute and app-owned voice-tool startup.

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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

LOG = logging.getLogger("reachy_tools.runtime")


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
                "speaker_muted": not self.enabled,
                "mode": "speaker_mute",
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
    """Per-session phrase assembly and app-owned voice-tool startup."""

    def __init__(self, state: State):
        """Track startup and incoming phrase fragments."""
        self.state = state
        self.local_calls = set()
        self.bootstrapped = False
        self.voice_available = False


class Runtime:
    """Relay every conversation event and control only the physical speaker mute."""

    def __init__(self, state: State, config: dict[str, Any]):
        """Own speaker controls independently of app generation and tools."""
        self.state, self.config = state, config
        self.gates = set()
        self.loop = None
        self.speech_lock = asyncio.Lock()

    async def apply_speaker(self, enabled: bool):
        """Toggle the ALSA playback switch without changing volume or microphone."""
        process = await asyncio.create_subprocess_exec(
            "amixer", "-c", self.config.get("speaker_card", "Audio"),
            "sset", "PCM,0", "unmute" if enabled else "mute",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 2)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        expected = b"[on]" if enabled else b"[off]"
        if process.returncode or expected not in stdout:
            raise RuntimeError("Speaker mute switch could not be confirmed")

    async def set_speech(self, enabled: bool):
        """Mute/unmute the speaker; leave generation, playback queues and tools alone."""
        async with self.speech_lock:
            previous = self.state.enabled
            await self.apply_speaker(enabled)
            try:
                self.state.set_enabled(enabled)
            except Exception:
                self.state.enabled = previous
                await self.apply_speaker(previous)
                raise
            LOG.info("SPEECH_CONTROL speaker_muted=%s; conversation and tools continue", not enabled)
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
                        await upstream.send(raw)

                async def server_events():
                    async for raw in upstream:
                        event = json.loads(raw)
                        kind = event.get("type", "")
                        if kind == "response.output_audio.delta":
                            self.state.audio_at = time.monotonic()
                            self.state.forwarded_audio += 1
                        await downstream.send(raw)
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
        await self.apply_speaker(self.state.enabled)
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
