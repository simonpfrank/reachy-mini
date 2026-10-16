"""Persistent speech control through the separately supervised loopback realtime relay.

The Tool entry point uses no app hooks. SpeechState below retains historical gate regression logic;
the live gate runs in conversation_runtime.py outside the installed app.
"""

import asyncio
import inspect
import json
import logging
import os
import re
import time
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

logger = logging.getLogger(__name__)
QUIET_COMMANDS = {"shut up", "be quiet", "stop talking", "stop speaking", "stop answering", "quiet"}
RESUME_COMMAND = re.compile(
    r"(?:you (?:can|may) (?:speak|talk)(?: again| now)?|(?:resume|start) (?:speaking|talking)(?: again)?)"
)


def command_enabled(text: str) -> bool | None:
    """Recognise explicit quiet/resume phrases, excluding quotes, negations and casual mentions."""
    normal = re.sub(r"[^a-z\s]", "", text.lower())
    normal = " ".join(normal.split())
    normal = re.sub(r"^(?:(?:marvin|reachy|please|okay|ok|its fine|all right) )+", "", normal)
    normal = re.sub(r" please$", "", normal)
    if normal in QUIET_COMMANDS:
        return False
    return True if RESUME_COMMAND.fullmatch(normal) else None


def state_path() -> Path:
    """Keep quiet state outside the installed app so updates and restarts retain it."""
    root = Path(os.environ.get("REACHY_TOOLS_STATE_DIR", "~/.config/reachy_tools")).expanduser()
    return root / "speech.json"


class SpeechState:
    """One reload-safe owner for input commands, playback gating and blocked response IDs."""

    def __init__(self, deps: ToolDependencies, stream: Any, path: Path | None = None) -> None:
        """Load the persisted switch before audio playback begins."""
        self.deps, self.stream = deps, stream
        self.path = path or state_path()
        self._lock = asyncio.Lock()
        self._quiet = False
        self._active_response: str | None = None
        self._blocked: deque[str] = deque(maxlen=128)
        self.last_audio_at = float("-inf")
        self.persistence_error: str | None = None
        self.generation = 0
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                if not isinstance(data.get("enabled"), bool):
                    raise ValueError("enabled must be a boolean")
                self._quiet = not data["enabled"]
            except (OSError, ValueError, AttributeError) as error:
                self._quiet = True
                self.persistence_error = str(error)
                logger.error("SPEECH_CONTROL state unreadable; remaining quiet: %s", error)

    @property
    def quiet(self) -> bool:
        """Whether audio output and model-triggered actions are currently suppressed."""
        return self._quiet

    def status(self) -> dict[str, Any]:
        """Expose the actual state to tools, RPC and telemetry."""
        return {"enabled": not self._quiet, "quiet": self._quiet, "persistence_error": self.persistence_error}

    def _save(self, enabled: bool) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump({"enabled": enabled}, output)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(self.path)

    async def set_enabled(self, enabled: bool, source: str = "tool") -> dict[str, Any]:
        """Flush playback and persist the mode before allowing speech to resume."""
        async with self._lock:
            if self._active_response and self._active_response not in self._blocked:
                self._blocked.append(self._active_response)
            # Gate immediately, including while the state is written and old audio is flushed.
            self._quiet = True
            self.generation += 1
            flushed = self.stream.clear_audio_queue()
            if inspect.isawaitable(flushed):
                await flushed
            pending = getattr(getattr(self.stream, "handler", None), "_pending_responses", None)
            if isinstance(pending, asyncio.Queue):
                while not pending.empty():
                    pending.get_nowait()
            try:
                self._save(enabled)
            except OSError as error:
                self.persistence_error = str(error)
                logger.error("SPEECH_CONTROL state could not be saved; remaining quiet: %s", error)
                raise
            self._quiet = not enabled
            self.persistence_error = None
            logger.info("SPEECH_CONTROL enabled=%s source=%s", str(enabled).lower(), source)
            handler = getattr(self.stream, "handler", None)
            if handler is not None:
                handler._mark_activity("speech_resumed" if enabled else "speech_quiet")
            rpc = getattr(self.stream, "_rpc", None)
            if rpc is not None:
                rpc.broadcast_threadsafe("conversation.speech", self.status())
            return self.status()

    async def handle_text(self, text: str, source: str = "typed") -> bool:
        """Handle control commands locally; consume other requests while quiet."""
        enabled = command_enabled(text)
        if enabled is not None:
            await self.set_enabled(enabled, source)
            return True
        return self._quiet

    async def cancel_response(self, handler: Any) -> None:
        """Best-effort generation cancellation; local gates remain authoritative."""
        try:
            if handler.connection is not None:
                await handler.connection.response.cancel()
        except Exception as error:
            # Playback and tool gates remain effective if the backend cannot cancel generation.
            logger.debug("SPEECH_CONTROL backend cancellation unavailable: %s", error)

    async def on_event(self, event: Any, handler: Any) -> bool:
        """Inspect inputs and suppress output for quiet or previously blocked responses."""
        kind = event.type
        if kind == "response.created":
            self._active_response = getattr(event.response, "id", None)
            if self._quiet:
                if self._active_response:
                    self._blocked.append(self._active_response)
                await self.cancel_response(handler)
        elif kind == "conversation.item.input_audio_transcription.completed":
            text = getattr(event, "transcript", "") or ""
            enabled = command_enabled(text)
            if enabled is not None:
                await self.set_enabled(enabled, "voice")
                if not enabled:
                    await self.cancel_response(handler)
        elif kind == "conversation.item.input_audio_transcription.delta":
            # Quiet commands may be acted on early; resume requires a completed transcript.
            if not self._quiet and command_enabled(getattr(event, "delta", "") or "") is False:
                await self.set_enabled(False, "voice_partial")
                await self.cancel_response(handler)
        response_id = getattr(event, "response_id", None) or self._active_response
        blocked = self._quiet or (response_id is not None and response_id in self._blocked)
        if kind == "response.function_call_arguments.done" and blocked:
            try:
                await handler.connection.conversation.item.create(
                    item={
                        "type": "function_call_output",
                        "call_id": event.call_id,
                        "output": json.dumps({"status": "quiet", "executed": False}),
                    }
                )
            except Exception as error:
                logger.debug("SPEECH_CONTROL suppressed tool reply could not be sent: %s", error)
            return True
        if (
            kind
            in {
                "response.output_audio.delta",
                "response.output_audio_transcript.done",
                "response.output_text.delta",
                "response.output_text.done",
            }
            and blocked
        ):
            return True
        if kind == "response.output_audio.delta":
            self.last_audio_at = time.monotonic()
        if kind == "response.done":
            self._active_response = None
        return False


class SpeechControl(Tool):  # type: ignore[misc]
    """Stop current audio and stay quiet, or explicitly restore speaking."""

    name = "speech_control"
    description = (
        "Control robot speech. enabled=false immediately stops current audio and stays quiet until explicitly "
        "told it can speak again. enabled=true resumes speaking only on that explicit request. "
        "Do not speak an acknowledgement when switching off. Omit enabled to read the actual state."
    )
    needs_response = False
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"enabled": {"type": "boolean"}},
        "required": [],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Use the external relay's control API, without injected app state or methods."""
        if "enabled" in kwargs and not isinstance(kwargs["enabled"], bool):
            raise ValueError("enabled must be boolean")

        def request() -> dict[str, Any]:
            payload = {"enabled": kwargs["enabled"]} if "enabled" in kwargs else None
            route = "/speech" if payload is not None else "/state"
            req = urllib.request.Request(
                f"http://127.0.0.1:{int(os.environ.get('REACHY_TOOLS_CONTROL_PORT', '8767'))}" + route,
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={"Content-Type": "application/json"},
                method="POST" if payload is not None else "GET",
            )
            with urllib.request.urlopen(req, timeout=6) as response:  # noqa: S310 -- fixed loopback
                result: dict[str, Any] = json.load(response)
            return result

        return await asyncio.to_thread(request)
