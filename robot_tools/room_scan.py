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
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reachy_mini.motion.move import Move  # type: ignore[import-untyped]
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the app loads tools by path; see reachy_lib
from reachy_lib import motion  # noqa: E402
from reachy_lib.detection import PASSES, ModelSpec, availability, load_models, load_tiers  # noqa: E402
from reachy_lib.detector import Detection, Detector, decode_jpeg, engine_available  # noqa: E402
from reachy_lib.replies import checked  # noqa: E402
from reachy_lib.scan_settings import ScanSettings, read_tables  # noqa: E402
from reachy_lib.storage import scan_dir, write_private  # noqa: E402
from reachy_lib.world import build_world, read_world, write_world  # noqa: E402

LOG = logging.getLogger(__name__)
TASK_KEY = "_room_scan_task"  # kept on the movement manager so a tool reload still sees a running scan


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
    step = settings.hfov_deg * settings.crop * (1 - settings.overlap)  # overlap is of the trimmed field
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


def load_detector(spec: ModelSpec, settings: ScanSettings) -> Detector:
    """Open a model's file as a detector with this scan's cut-offs and thread count."""
    return Detector.load(spec, threads=settings.analysis_threads, conf=settings.confidence, iou=settings.nms_iou)


def _analyse_stop(detector: Detector, jpeg: bytes, crop: float, tier: str) -> list[dict[str, Any]]:
    """Decode one photo, keep the central ``crop`` of its width, detect, and put the boxes back in photo pixels."""
    image = decode_jpeg(jpeg)
    trim = int(image.shape[1] * (1 - crop) / 2)
    found: list[Detection] = detector.detect(image[:, trim : image.shape[1] - trim])
    return [
        {
            "label": d.label,
            "score": round(d.score, 3),
            "box": [round(d.box[0] + trim), round(d.box[1]), round(d.box[2] + trim), round(d.box[3])],
            "tier": tier,
        }
        for d in found
    ]


def _summary(found: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for item in found:
        counts[item["label"]] = counts.get(item["label"], 0) + 1
    return ", ".join(f"{label} {count}" for label, count in counts.items()) or "nothing found"


class Analysis:
    """The detection passes of one scan, and the record of what each did (``analysis.json``).

    Pass ``now`` runs on each photo as it is taken, so knowledge grows during the scan. Pass ``after`` runs over
    every photo once the robot is back. Pass ``remote`` (the Mac) is recorded as not built yet. A pass that cannot
    run is recorded with the reason and never stops the scan. Results are anonymous: a label, a score and a box.
    """

    def __init__(self, settings: ScanSettings, total: int) -> None:
        """Read the model and tier tables from scan.json; a mistake there is recorded, not fatal."""
        self.settings, self.total = settings, total
        self.passes: dict[str, dict[str, Any]] = {}
        self.found: dict[str, dict[int, list[dict[str, Any]]]] = {"now": {}, "after": {}}
        self._used: set[str] = set()
        self._tasks: dict[int, asyncio.Task[list[dict[str, Any]]]] = {}
        self._detector: Detector | None = None
        self._error = ""
        self.on_change: Callable[[], None] | None = None  # called each time a photo's results arrive
        try:
            models_table, tiers_table = read_tables()
            self.models = load_models(models_table)
            self.tiers = load_tiers(self.models, tiers_table)
        except ValueError as error:
            self._error = str(error)
            self.models = load_models()
            self.tiers = load_tiers(self.models)

    async def start(self) -> None:
        """Open the ``now`` detector before the robot moves, so loading never delays a photo."""
        self._detector = await self._open("now")

    def submit(self, stop: Stop) -> None:
        """Start analysing a photo the moment it is taken, while the robot moves on to the next stop."""
        if self._detector is not None and stop.jpeg is not None:
            self._tasks[stop.index] = asyncio.create_task(self._analyse(self._detector, stop, "now"))

    async def finish_now(self, elapsed: Callable[[], float]) -> None:
        """Wait for the ``now`` analyses still running and record how that pass went."""
        if self._detector is None:
            return
        results = await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        failed = [result for result in results if isinstance(result, BaseException)]
        self._record("now", failed, len(results), elapsed)

    async def run_after(self, stops: list[Stop], elapsed: Callable[[], float]) -> None:
        """Run the ``after`` model over every photo, one at a time; also record the (unbuilt) ``remote`` pass."""
        detector = await self._open("after")
        await self._open("remote")
        if detector is None:
            return
        failed: list[BaseException] = []
        for stop in stops:
            if stop.jpeg is None:
                continue
            try:
                await self._analyse(detector, stop, "after")
            except Exception as error:
                failed.append(error)
        self._record("after", failed, len(stops), elapsed)

    def cancel(self) -> None:
        """Stop any analysis still running (the scan is being abandoned)."""
        for task in self._tasks.values():
            task.cancel()

    def save(self, stops: list[Stop], reason: str, started: str) -> None:
        """Write ``analysis.json`` beside the photos, replacing the last one: it must never describe an older scan."""
        for name in PASSES:
            self.passes.setdefault(
                name,
                {"model": self.tiers[name], "status": "skipped", "reason": "the scan ended first", "seconds": None},
            )
        per_stop = [
            {"index": s.index, "passes": {t: self.found[t][s.index] for t in self.found if s.index in self.found[t]}}
            for s in stops
        ]
        data = {
            "scan_started": started,
            "reason": reason,
            "crop": self.settings.crop,
            "passes": self.passes,
            "stops": per_stop,
        }
        write_private(scan_dir(), {"analysis.json": json.dumps(data, indent=2).encode()})

    async def _open(self, name: str) -> Detector | None:
        """The detector for one pass, or None with the reason recorded: switched off, not built, or not available."""
        model = self.tiers[name]
        record: dict[str, Any] = {"model": model, "status": "skipped", "reason": "", "seconds": None}
        self.passes[name] = record
        record["reason"] = self._skip_reason(name, model)
        if record["reason"]:
            return None
        try:
            detector = await asyncio.to_thread(load_detector, self.models[str(model)], self.settings)
        except Exception as error:
            record.update(status="failed", reason=f"could not load {model}: {type(error).__name__}")
            return None
        self._used.add(str(model))
        record.update(status="ready", reason="ok")
        return detector

    def _skip_reason(self, name: str, model: str | None) -> str:
        if self._error:
            return f"scan.json: {self._error}"
        if model is None:
            return "switched off"
        if name == "remote":
            return "remote analysis is not built yet"
        if model in self._used:
            return f"same model as an earlier pass ({model})"
        ready, reason = engine_available()
        if not ready:
            return reason
        ready, reason = availability(self.models[model])
        return "" if ready else reason

    async def _analyse(self, detector: Detector, stop: Stop, tier: str) -> list[dict[str, Any]]:
        found = await asyncio.to_thread(_analyse_stop, detector, stop.jpeg or b"", self.settings.crop, tier)
        LOG.info("room scan analysis (%s): photo %d of %d: %s", tier, stop.index + 1, self.total, _summary(found))
        self.found[tier][stop.index] = found  # kept the moment it arrives: knowledge grows during the scan
        if self.on_change:
            self.on_change()
        return found

    def _record(self, name: str, failed: list[BaseException], count: int, elapsed: Callable[[], float]) -> None:
        record = self.passes[name]
        record["seconds"] = round(elapsed(), 1)
        if failed:
            record.update(status="failed", reason=f"{type(failed[0]).__name__} on {len(failed)} of {count} photos")
        else:
            record.update(status="ran", reason="ok")
        LOG.info(
            "room scan analysis: pass %s (%s) %s on %d photos, %.1f s into the scan",
            name, record["model"], record["status"], count, record["seconds"],
        )  # fmt: skip


class WorldPublisher:
    """Builds and saves the robot's picture of the room (``world.json``) each time something new is known.

    The picture that was there before the scan is read once and kept as stale until the new scan completes. Saving
    is best effort: a failure is logged and never stops the scan.
    """

    def __init__(
        self, settings: ScanSettings, analysis: Analysis, stops: list[Stop], total: int, resolution: list[int]
    ) -> None:
        """Remember what the picture is built from; ``stops`` is the list the scan keeps adding photos to."""
        self._settings, self._analysis, self._stops = settings, analysis, stops
        self._total, self._resolution = total, resolution
        self._started = datetime.now(UTC).isoformat(timespec="seconds")
        try:
            self._previous = read_world()
        except ValueError:
            LOG.warning("the previous room picture is damaged and is ignored")
            self._previous = None

    def publish(self, status: str) -> None:
        """Rebuild the picture from what is known now and save it: ``scanning``, ``complete`` or ``partial``."""
        found = self._analysis.found
        try:
            write_world(
                build_world(
                    photos=[(stop.index, math.degrees(stop.measured.heading)) for stop in self._stops],
                    detections=found,
                    ran_tiers=tuple(tier for tier in ("now", "after") if found[tier]),
                    status=status,
                    total=self._total,
                    scan_started=self._started,
                    now=datetime.now(UTC).isoformat(timespec="seconds"),
                    previous=self._previous,
                    width=self._resolution[0],
                    height=self._resolution[1],
                    hfov_deg=self._settings.hfov_deg,
                    tolerance_deg=self._settings.merge_tolerance_deg,
                    overlap=self._settings.merge_overlap,
                )
            )
        except Exception:
            LOG.exception("could not save the room picture")


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
    analysis = Analysis(settings, len(poses))
    world = WorldPublisher(settings, analysis, stops, len(poses), resolution)
    analysis.on_change = lambda: world.publish("scanning")
    await analysis.start()  # the pass-1 model is opened now, so loading never delays a photo
    world.publish("scanning")  # from here the previous picture is stale
    reachy.disable_wobbling()  # speech wobble would move the head during a photo
    began = clock()
    deps.movement_manager.queue_move(move)
    try:
        for index, (pose, moment) in enumerate(zip(poses, photo_times, strict=True)):
            await asyncio.sleep(max(0.0, began + moment - clock()))
            stops.append(await _capture(reachy, index, pose))
            analysis.submit(stops[-1])  # analysed while the robot moves on
        await asyncio.sleep(max(0.0, began + move.duration - clock()))  # the move itself brings the robot back
        await analysis.finish_now(lambda: clock() - began)
        await analysis.run_after(stops, lambda: clock() - began)
    finally:
        analysis.cancel()
        reachy.enable_wobbling()
        complete = await asyncio.to_thread(save_scan, stops, len(poses), settings, reason, started, resolution)
        await asyncio.to_thread(analysis.save, stops, reason, started)
        world.publish("complete" if complete else "partial")
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
        "privately on the robot and you cannot see them. The scan analyses them as it goes: once it has started, "
        "use room_view to say what has been found so far and how complete that is, and never claim to know what is "
        "in the room beyond what room_view returns. Replies at once; the scan takes about 40 seconds."
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
        settings = ScanSettings.load(os.environ)
        store[TASK_KEY] = asyncio.create_task(_run_in_background(deps, settings))
        return {
            "started": True,
            "note": "Scanning the room now; it takes about 40 seconds. The photos are saved privately on the robot "
            "and you cannot see them. Results arrive as it goes: use room_view to say what has been found so far, "
            "and say nothing beyond that.",
        }
