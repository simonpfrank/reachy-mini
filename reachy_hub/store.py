"""Hold the hub's current view: latest robot state, live levels, link status, recent events.

Everything runs on one asyncio loop, so no locking is needed.

Usage:
    store = Store()
    store.add_rpc(message, datetime.now(UTC))
    page_data = store.snapshot()
"""

from collections import deque
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any

from reachy_hub.events import Event, ImuReading, RobotState, event_from_rpc, imu_reading, robot_state_from_full
from reachy_hub.imu import Tap, TapDetector
from reachy_hub.logs import event_from_log_line

LEVEL_EVENT = "conversation.level"


@dataclass(frozen=True)
class _Stream:
    """A run of streaming chunks (e.g. the robot's audio) shown as one started/ended pair."""

    key: str
    started: datetime
    last: datetime
    chunks: int
    last_text: str | None = None


def _stream_key(event: Event) -> str | None:
    """Name of the stream a chunk event belongs to, or None if it is not a streaming chunk."""
    reason = event.data.get("reason")
    if event.kind == "conversation.activity" and isinstance(reason, str) and reason.endswith("_delta"):
        return reason
    if event.kind == "conversation.transcript" and event.data.get("final") is False:
        return f"transcript.{event.data.get('role')}"
    return None


class Store:
    """Latest values plus a capped, numbered list of events."""

    def __init__(self, max_events: int = 500, since: datetime | None = None) -> None:
        """Create an empty store.

        Args:
            max_events: Most events kept (oldest dropped).
            since: Ignore log lines older than this (default: now). The log stream
                replays its last 100 lines on every connect.
        """
        self._since = since or datetime.now(UTC)
        self.log_link = "not started"
        self._seen_lines: deque[str] = deque(maxlen=300)
        self._open_tool_calls: dict[str, datetime] = {}  # call_id -> when the AI asked for it
        self.robot: RobotState | None = None
        self.user_level: float | None = None
        self.robot_level: float | None = None
        self.app_link = "not started"
        self.robot_link = "not started"
        self.imu_link = "not started"
        self.imu: ImuReading | None = None
        self.last_tap: tuple[datetime, Tap] | None = None
        self._taps = TapDetector()
        self._stream: _Stream | None = None
        self._speech_started: datetime | None = None
        self._speech_peak = 0.0
        self._events: deque[tuple[int, Event]] = deque(maxlen=max_events)
        self._seq = 0

    @property
    def events(self) -> list[Event]:
        """Events currently held, oldest first."""
        return [event for _, event in self._events]

    def _append(self, event: Event) -> None:
        self._seq += 1
        self._events.append((self._seq, event))

    def add_rpc(self, message: object, now: datetime | None = None) -> None:
        """Take one message from an app's ``/rpc``: levels update live values, the rest become events."""
        event = event_from_rpc(message, now or datetime.now(UTC))
        if event is None:
            return
        if event.kind != LEVEL_EVENT:
            key = _stream_key(event)
            if key is not None:
                self._continue_stream(key, event.time, event.data.get("text"))
                return
            self._end_stream()
            self._append(event)
            self._track_user_speech(event)
            return
        rms = event.data.get("rms")
        if event.data.get("role") == "user":
            self.user_level = rms
            if self._speech_started is not None and isinstance(rms, int | float):
                self._speech_peak = max(self._speech_peak, float(rms))
        else:
            self.robot_level = rms

    def _track_user_speech(self, event: Event) -> None:
        """On ``user_speech_stopped``, record ``speech.heard``: how long the user spoke and the mic's peak level.

        This is what was fed to speech-to-text (the audio itself stays on the backend).
        """
        reason = event.data.get("reason")
        if reason == "user_speech_started":
            self._speech_started, self._speech_peak = event.time, 0.0
        elif reason == "user_speech_stopped" and self._speech_started is not None:
            seconds = round((event.time - self._speech_started).total_seconds(), 2)
            heard = {"seconds": seconds, "peak_level": self._speech_peak}
            self._append(Event(event.time, "app", "speech.heard", heard))
            self._speech_started = None

    def _continue_stream(self, key: str, when: datetime, text: object = None) -> None:
        """Count a chunk in the current stream, or end it and start a new one."""
        last_text = text if isinstance(text, str) else None
        if self._stream is not None and self._stream.key == key:
            self._stream = replace(self._stream, last=when, chunks=self._stream.chunks + 1, last_text=last_text)
            return
        self._end_stream()
        self._append(Event(when, "app", "stream.started", {"stream": key}))
        self._stream = _Stream(key, when, when, 1, last_text)

    def _end_stream(self) -> None:
        """Record ``stream.ended`` (chunks, seconds) for the current stream, if any."""
        if self._stream is None:
            return
        s = self._stream
        seconds = round((s.last - s.started).total_seconds(), 2)
        data: dict[str, Any] = {"stream": s.key, "chunks": s.chunks, "seconds": seconds}
        if s.last_text is not None:
            data["last_text"] = s.last_text
        self._append(Event(s.last, "app", "stream.ended", data))
        self._stream = None

    def set_robot(self, payload: object) -> None:
        """Replace the robot state with the daemon's latest ``/api/state/full`` payload."""
        if isinstance(payload, dict):
            self.robot = robot_state_from_full(payload)

    def add_imu(self, payload: object, now: datetime | None = None) -> None:
        """Take one fast IMU reading: keep it live; on a tap, keep it as last tap and record ``imu.tap``."""
        imu = payload.get("imu") if isinstance(payload, dict) else None
        reading = imu_reading(imu)
        if reading is None or not isinstance(imu, dict):
            return
        when = now or datetime.now(UTC)
        self.imu = reading
        tap = self._taps.feed(when.timestamp(), imu["accelerometer"])
        if tap is not None:
            self.last_tap = (when, tap)
            self._append(Event(when, "robot", "imu.tap", asdict(tap)))

    def add_log_line(self, line: str) -> None:
        """Take one daemon log line: keep tracked events newer than ``since``, skip replays and duplicates.

        Tool calls are remembered by call id, so the matching ``tool.done``/``tool.failed``
        gets ``seconds``: how long the tool took.
        """
        if line in self._seen_lines:
            return
        self._seen_lines.append(line)
        event = event_from_log_line(line)
        if event is None or event.time < self._since:
            return
        if event.kind == "tool.call":
            self._open_tool_calls[str(event.data["call_id"])] = event.time
        elif event.kind in ("tool.done", "tool.failed") and event.data["id"] in self._open_tool_calls:
            started = self._open_tool_calls.pop(str(event.data["id"]))
            seconds = round((event.time - started).total_seconds(), 2)
            event = Event(event.time, event.source, event.kind, {**event.data, "seconds": seconds})
        self._append(event)

    def _imu_snapshot(self) -> dict[str, Any]:
        last_tap = None
        if self.last_tap:
            when, tap = self.last_tap
            last_tap = {"time": when.isoformat(), **asdict(tap)}
        return {"latest": asdict(self.imu) if self.imu else None, "last_tap": last_tap}

    def set_link(self, name: str, status: str, now: datetime | None = None) -> None:
        """Record a feed's connection status ("app", "robot", "imu" or "log"); log an event only when it changes."""
        attr = f"{name}_link"
        if getattr(self, attr) == status:
            return
        setattr(self, attr, status)
        self._append(Event(now or datetime.now(UTC), "hub", "link", {"name": name, "status": status}))

    def snapshot(self) -> dict[str, Any]:
        """Return everything the dashboard shows, as JSON-ready data."""
        return {
            "robot": asdict(self.robot) if self.robot else None,
            "user_level": self.user_level,
            "robot_level": self.robot_level,
            "app_link": self.app_link,
            "robot_link": self.robot_link,
            "imu_link": self.imu_link,
            "log_link": self.log_link,
            "imu": self._imu_snapshot(),
            "events": [
                {"seq": seq, "time": e.time.isoformat(), "source": e.source, "kind": e.kind, "data": dict(e.data)}
                for seq, e in self._events
            ],
        }
