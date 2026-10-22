"""On-device tool: scan the whole room as a fixed sequence of photos (roadmap 4c, phase 1: capture only).

The plan is a single row at one pitch over the robot's full reach, from one yaw limit to the other. Each step is
the camera's horizontal field of view reduced by the overlap, spread evenly so the last frame lands on the limit.
The body turns first; the head adds reach only beyond the body's limit. Every number that depends on the robot is
a setting (environment or ``.env``) to be recalibrated on the real robot.

The whole scan is one queued move (travel to a stop, hold, travel on, and finally back to where the robot was
facing), so nothing else moves the robot during it and the return does not depend on any cleanup running. The tool
starts it as a background task and replies at once: the speech backend will not respond while a tool call is
unanswered. A photo is taken in the middle of each hold and saved with its measured pose; only the latest scan is
kept. Nothing is analysed yet.
"""

import asyncio
import json
import logging
import math
import os
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reachy_mini.motion.move import Move  # type: ignore[import-untyped]
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the app loads tools by path; see reachy_lib
from reachy_lib import motion  # noqa: E402
from reachy_lib.replies import checked  # noqa: E402
from reachy_lib.storage import scan_dir, write_private  # noqa: E402

LOG = logging.getLogger(__name__)
TASK_KEY = "_room_scan_task"  # kept on the movement manager so a tool reload still sees a running scan


def _number(environ: Mapping[str, str], name: str, default: float) -> float:
    """A float setting; a value that is not a number is refused, naming the setting."""
    raw = environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a number, got {raw!r}") from error


@dataclass(frozen=True)
class ScanSettings:
    """What the scan needs to know about the robot, with the agreed defaults.

    Attributes:
        overlap: Fraction of each frame shared with the next, from 0 up to but not including 1.
        hfov_deg: Camera horizontal field of view.
        body_min_deg: Body yaw limit on the right (negative; SDK sign, positive is left).
        body_max_deg: Body yaw limit on the left. The limits need not be equal.
        head_min_deg: Head yaw limit relative to the body, right (negative).
        head_max_deg: Head yaw limit relative to the body, left.
        pitch_deg: Head pitch for the whole row.
        settle_s: Seconds the robot is given to stop moving before a photo (it holds twice as long at each stop).
    """

    overlap: float = 0.25
    hfov_deg: float = 87.0
    body_min_deg: float = -125.0  # measured cable limits with a margin, as in voice_look; recalibrate on the robot
    body_max_deg: float = 140.0
    head_min_deg: float = -35.0  # voice_look's head reach; the SDK allows 65
    head_max_deg: float = 35.0
    pitch_deg: float = 0.0
    settle_s: float = 0.5

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "ScanSettings":
        """Read ``REACHY_SCAN_*`` settings from ``environ``.

        Args:
            environ: Environment-like mapping, normally ``os.environ``.

        Returns:
            The settings, with defaults for anything not set.

        Raises:
            ValueError: A value is not a number, the overlap is outside 0 <= overlap < 1, the settle time is
                negative, or a yaw range does not include zero (the plan relies on straight ahead being reachable).
        """
        defaults = cls()
        overlap = _number(environ, "REACHY_SCAN_OVERLAP", defaults.overlap)
        if not 0 <= overlap < 1:
            raise ValueError(f"REACHY_SCAN_OVERLAP must be from 0 up to but not including 1, got {overlap}")
        settle = _number(environ, "REACHY_SCAN_SETTLE_S", defaults.settle_s)
        if settle < 0:
            raise ValueError(f"REACHY_SCAN_SETTLE_S must not be negative, got {settle}")
        settings = cls(
            overlap=overlap,
            hfov_deg=_number(environ, "REACHY_SCAN_HFOV_DEG", defaults.hfov_deg),
            body_min_deg=_number(environ, "REACHY_SCAN_BODY_YAW_MIN_DEG", defaults.body_min_deg),
            body_max_deg=_number(environ, "REACHY_SCAN_BODY_YAW_MAX_DEG", defaults.body_max_deg),
            head_min_deg=_number(environ, "REACHY_SCAN_HEAD_YAW_MIN_DEG", defaults.head_min_deg),
            head_max_deg=_number(environ, "REACHY_SCAN_HEAD_YAW_MAX_DEG", defaults.head_max_deg),
            pitch_deg=_number(environ, "REACHY_SCAN_PITCH_DEG", defaults.pitch_deg),
            settle_s=settle,
        )
        ranges = (
            ("BODY", settings.body_min_deg, settings.body_max_deg),
            ("HEAD", settings.head_min_deg, settings.head_max_deg),
        )
        for part, low, high in ranges:
            if not low <= 0 <= high:
                raise ValueError(
                    f"REACHY_SCAN_{part}_YAW_MIN_DEG and REACHY_SCAN_{part}_YAW_MAX_DEG must bracket zero, "
                    f"got {low} to {high}"
                )
        return settings


@dataclass(frozen=True)
class ScanPose:
    """One stop in the scan: where the body and head point, in degrees."""

    body_yaw_deg: float
    head_yaw_deg: float
    pitch_deg: float


def plan(settings: ScanSettings) -> list[ScanPose]:
    """The fixed pose sequence for these settings, from the right-hand limit to the left-hand limit.

    Args:
        settings: Robot limits, field of view and overlap.

    Returns:
        Poses in order. The camera heading is body yaw plus head yaw; headings are evenly spaced and every pose
        is within the body and head limits.
    """
    first = settings.body_min_deg + settings.head_min_deg  # camera heading at the right-hand limit
    last = settings.body_max_deg + settings.head_max_deg
    step = settings.hfov_deg * (1 - settings.overlap)
    gaps = max(1, math.ceil((last - first) / step - 1e-9))
    poses = []
    for index in range(gaps + 1):
        heading = first + (last - first) * index / gaps
        body = max(settings.body_min_deg, min(settings.body_max_deg, heading))
        poses.append(ScanPose(body, heading - body, settings.pitch_deg))
    return poses


class ScanMove(Move):  # type: ignore[misc]
    """Every leg of the scan as one move: travel to a stop, hold there, travel on, and finally back to the start."""

    def __init__(self, legs: list[tuple[motion.PoseMove, float]]) -> None:
        """Join the legs, each a move and the seconds to hold at its end."""
        self._legs = legs
        self._duration = sum(move.duration + hold for move, hold in legs)

    @property
    def duration(self) -> float:
        """Seconds from the first movement to the robot being back at the start."""
        return self._duration

    def evaluate(self, t: float) -> tuple[Any, Any, float]:
        """The pose at time ``t``; a finished leg stays on its target while it is held."""
        for move, hold in self._legs:
            if t < move.duration + hold:
                return move.evaluate(t)  # PoseMove stays on its target once its own time is up
            t -= move.duration + hold
        last = self._legs[-1][0]
        return last.evaluate(last.duration)


def build_scan(start: motion.PoseSnapshot, poses: list[ScanPose], settle_s: float) -> tuple[ScanMove, list[float]]:
    """The one move that visits every pose and returns to ``start``, and when to take each photo.

    Args:
        start: The pose to come back to; also keeps roll, position and antennas unchanged during the scan.
        poses: The stops, in order.
        settle_s: Seconds to wait after arriving before the photo; the robot holds twice as long.

    Returns:
        The move, and seconds after it starts at which each photo should be taken (in the middle of the hold).
    """
    legs: list[tuple[motion.PoseMove, float]] = []
    photo_times: list[float] = []
    here, elapsed = start, 0.0
    for pose in poses:
        target = motion.facing(start, pose.body_yaw_deg + pose.head_yaw_deg, pose.body_yaw_deg, pose.pitch_deg)
        leg = motion.PoseMove(here, target)
        legs.append((leg, 2 * settle_s))
        photo_times.append(elapsed + leg.duration + settle_s)
        elapsed += leg.duration + 2 * settle_s
        here = target
    legs.append((motion.PoseMove(here, start), 0.0))
    return ScanMove(legs), photo_times


@dataclass(frozen=True)
class Stop:
    """One photo of the scan: where it was meant to be taken, where the robot measured itself, and the image."""

    index: int
    planned: ScanPose
    jpeg: bytes | None
    measured: motion.PoseSnapshot
    taken: str


async def _capture(reachy: Any, index: int, planned: ScanPose) -> Stop:
    """Take one frame and note the pose the robot measures at that moment."""
    jpeg = await asyncio.to_thread(reachy.media.get_frame_jpeg)
    measured = motion.snapshot(reachy)
    return Stop(index, planned, jpeg or None, measured, datetime.now(UTC).isoformat(timespec="milliseconds"))


def _measured_degrees(pose: motion.PoseSnapshot) -> dict[str, float]:
    return {
        "heading_deg": round(math.degrees(pose.heading), 2),
        "body_yaw_deg": round(math.degrees(pose.body), 2),
        "pitch_deg": round(math.degrees(pose.pitch), 2),
        "roll_deg": round(math.degrees(pose.roll), 2),
    }


def save_scan(
    stops: list[Stop], total: int, settings: ScanSettings, reason: str, started: str, resolution: list[int]
) -> bool:
    """Replace the saved scan with these photos and a manifest; returns whether every photo was taken."""
    files: dict[str, bytes] = {}
    entries = []
    for stop in stops:
        name = f"scan_{stop.index:02}.jpg"
        if stop.jpeg:
            files[name] = stop.jpeg
        entries.append(
            {
                "index": stop.index,
                "file": name if stop.jpeg else None,
                "planned": asdict(stop.planned),
                "measured": _measured_degrees(stop.measured),
                "time": stop.taken,
            }
        )
    complete = len(stops) == total and all(stop.jpeg for stop in stops)
    manifest = {
        "reason": reason,
        "started": started,
        "complete": complete,
        "resolution": resolution,
        "settings": asdict(settings),
        "stops": entries,
    }
    files["scan.json"] = json.dumps(manifest, indent=2).encode()
    directory = scan_dir()
    write_private(directory, files)
    for old in directory.glob("scan_*.jpg"):
        if old.name not in files:
            old.unlink()
    return complete


async def run_scan(deps: ToolDependencies, settings: ScanSettings, reason: str) -> dict[str, Any]:
    """Run one scan to the end: queue the move, photograph each stop, save. The move brings the robot back itself.

    Args:
        deps: The app's robot and movement manager.
        settings: Limits, overlap and timing.
        reason: Why the scan was started (``requested``, later ``wake``, ``loud_noise`` and so on); saved with it.

    Returns:
        How many photos were taken, whether the scan is complete, and where it was saved.

    Raises:
        OSError: The camera failed. The partial scan is still saved and the move still returns the robot.
    """
    reachy = deps.reachy_mini
    start = motion.snapshot(reachy)
    poses = plan(settings)
    move, photo_times = build_scan(start, poses, settings.settle_s)
    started = datetime.now(UTC).isoformat(timespec="seconds")
    resolution = list(reachy.media.camera.resolution)
    stops: list[Stop] = []
    clock = asyncio.get_running_loop().time
    reachy.disable_wobbling()  # speech wobble would move the head during a photo
    began = clock()
    deps.movement_manager.queue_move(move)
    try:
        for index, (pose, moment) in enumerate(zip(poses, photo_times, strict=True)):
            await asyncio.sleep(max(0.0, began + moment - clock()))
            stops.append(await _capture(reachy, index, pose))
        await asyncio.sleep(max(0.0, began + move.duration - clock()))  # the move itself brings the robot back
    finally:
        reachy.enable_wobbling()
        complete = await asyncio.to_thread(save_scan, stops, len(poses), settings, reason, started, resolution)
    LOG.info("room scan finished: %d photos, complete=%s, reason=%s", len(stops), complete, reason)
    return {"stops": len(stops), "complete": complete, "folder": str(scan_dir())}


async def _run_in_background(deps: ToolDependencies, settings: ScanSettings) -> None:
    """Run a requested scan, logging how it ended; nothing is waiting on it."""
    try:
        await run_scan(deps, settings, "requested")
    except Exception:
        LOG.exception("room scan failed")


class RoomScan(Tool):  # type: ignore[misc]
    """Start a scan of the room and reply at once."""

    name = "room_scan"
    description = (
        "Looks all the way round the room: the robot turns through its whole range, taking a photo at fixed "
        "steps, then turns back to where it was facing and carries on. Use it when the user wants the robot to "
        "scan or look around the room, to check the room, or asks what or who is in the room. The photos are kept "
        "privately on the robot and cannot be analysed or described yet, so you cannot see them: never claim to "
        "know what is in the room, only that a scan was taken. Replies at once; the scan takes about 40 seconds."
    )
    parameters_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    @checked
    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Start the scan as a background task; one at a time, and never while the robot is moving."""
        store = vars(deps.movement_manager)
        running = store.get(TASK_KEY)
        if running is not None and not running.done():
            return {"error": "A room scan is already running."}
        if deps.movement_manager.get_status().get("queue_size"):
            return {"error": "The robot is moving; try the scan again in a moment."}
        settings = ScanSettings.from_env(os.environ)
        store[TASK_KEY] = asyncio.create_task(_run_in_background(deps, settings))
        return {
            "started": True,
            "note": "Scanning the room now; it takes about 40 seconds. The photos are saved privately "
            "on the robot and you cannot see them yet, so do not say what is in the room.",
        }
