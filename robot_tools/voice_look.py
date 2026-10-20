"""Turn the head and body toward whoever is speaking.

Started by a normal tool call; the tool description asks the model to call it at the start of every
conversation, whatever the personality. The call starts an
asyncio task inside the app and replies at once: the speech backend refuses to respond while a tool call
is unanswered, so the tool must never wait for the worker. Uses the public movement queue/status methods,
SDK sensing and BreathingMove's Move contract, and reads the movement manager's speaking flag to ignore
the robot's own voice. No relay, app hooks, import-time workers, direct daemon motor commands or
installed-code changes.
"""

import asyncio
import contextlib
import json
import logging
import math
import statistics
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from reachy_mini_conversation_app.moves import BreathingMove
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the app loads tools by path; see reachy_lib
from reachy_lib.motion import PoseMove, PoseSnapshot, angular_delta, from_pose, travel_seconds  # noqa: E402

logger = logging.getLogger(__name__)

DOA_URL = "http://localhost:8000/api/state/doa"
POLL_S = 0.1
WINDOW_S = 1.0
MIN_READINGS = 3
GROUP_WIDTH_DEG = 40.0
TURN_IF_OFF_BY_DEG = 20.0
HEAD_REACH_DEG = 35.0
BODY_LIMITS_DEG = (-125.0, 140.0)  # measured cable limits, with a margin
MOVE_S = 1.0
SETTLE_S = 0.4
STOP_TIMEOUT_S = 2.5  # longer than the DOA request timeout; never replace a worker that has not exited
MIN_EVIDENCE_S = 0.3
MIN_DOMINANCE = 0.7


def densest_group(values: list[float], width: float) -> list[float]:
    """The largest group of values that all lie within ``width`` of each other."""
    ordered = sorted(values)
    best: list[float] = []
    low = 0
    for high, value in enumerate(ordered):
        while value - ordered[low] > width:
            low += 1
        if high - low + 1 > len(best):
            best = ordered[low : high + 1]
    return best


def plan_turn(heading_deg: float, body_deg: float) -> tuple[float, float]:
    """Return (head heading, body yaw) in degrees from the base, keeping the head within reach of the body."""
    # Pick the nearest reachable circular bearing, then prefer less body travel at equal angular error.
    normal = angular_delta(heading_deg, 0.0)
    low, high = BODY_LIMITS_DEG[0] - HEAD_REACH_DEG, BODY_LIMITS_DEG[1] + HEAD_REACH_DEG
    choices = [max(low, min(high, normal + shift)) for shift in (-360.0, 0.0, 360.0)]
    heading_deg = min(choices, key=lambda value: (abs(angular_delta(value, normal)), abs(value - body_deg)))
    offset = heading_deg - body_deg
    if abs(offset) > HEAD_REACH_DEG:
        body_deg = heading_deg - math.copysign(HEAD_REACH_DEG, offset)
    body_deg = max(BODY_LIMITS_DEG[0], min(BODY_LIMITS_DEG[1], body_deg))
    heading_deg = max(body_deg - HEAD_REACH_DEG, min(body_deg + HEAD_REACH_DEG, heading_deg))
    return heading_deg, body_deg


def turn_duration(heading: float, body: float, target_heading: float, target_body: float) -> float:
    """Allow the physical yaw path enough time, including a long turn around cable limits."""
    unwrapped_heading = body + angular_delta(heading, body)
    return travel_seconds(target_heading - unwrapped_heading, target_body - body, MOVE_S)


def _read_doa() -> tuple[float, bool] | None:
    with urllib.request.urlopen(DOA_URL, timeout=1.0) as response:
        data = json.load(response)
    return (float(data["angle"]), bool(data["speech_detected"])) if data else None


class FacingBreath(BreathingMove):  # type: ignore[misc]
    """An interruptible idle move, with an externally owned target and smooth physical yaw path."""

    def __init__(
        self,
        pose: Any,
        antennas: tuple[float, float],
        start_body: float,
        heading: float,
        body: float,
        duration: float = MOVE_S,
    ) -> None:
        """Use the base constructor's public signature; the interpolation is the shared PoseMove."""
        super().__init__(pose, antennas, duration)
        self._seconds = duration
        rest = PoseSnapshot(0.0, 0.0, 0.0, 0.0, 0.0, heading, body, antennas)  # level, centred, facing the target
        self._move = PoseMove(from_pose(pose, start_body, antennas), rest, duration)

    def evaluate(self, t: float) -> tuple[Any, Any, float]:
        """Implement the SDK Move contract: the shared move, plus a slow breathing sway once it has arrived."""
        head, antennas, body = self._move.evaluate(t)
        if t >= self._seconds:
            head[2, 3] += 0.003 * math.sin(2 * math.pi * 0.1 * (t - self._seconds))
        return head, antennas, body


class StockFollower:
    """One cancellable worker task in the app's event loop; the tool call only starts or stops it."""

    def __init__(self, deps: ToolDependencies) -> None:
        """Keep ownership on the injected movement manager across tool reloads."""
        self.deps = deps
        self.running = False
        self.task: asyncio.Task[Any] | None = None
        self.worker = uuid.uuid4().hex[:12]
        self.readings: list[tuple[float, float]] = []
        self.target: tuple[float, float] | None = None
        self.busy_until = 0.0
        self.holding = False

    def pose(self) -> tuple[Any, float, float, tuple[float, float]]:
        """Use public SDK snapshots for sensing; command planning uses manager status below."""
        pose = self.deps.reachy_mini.get_current_head_pose()
        joints, antennas = self.deps.reachy_mini.get_current_joint_positions()
        heading = math.degrees(math.atan2(pose[1, 0], pose[0, 0]))
        return pose, heading, math.degrees(float(joints[0])), (float(antennas[0]), float(antennas[1]))

    def queue(
        self, target: tuple[float, float], now: float, reason: str, heard: float | None = None, readings: int = 0
    ) -> None:
        """Only the app movement queue writes motion; never clear or overwrite a gesture."""
        pose, heading, body, antennas = self.pose()
        command = self.deps.movement_manager.get_status().get("last_commanded_pose", {})
        matrix = command.get("head")
        if matrix is not None:
            heading = math.degrees(math.atan2(matrix[1][0], matrix[0][0]))
        if command.get("body_yaw") is not None:
            body = math.degrees(command["body_yaw"])
        duration = turn_duration(heading, body, *target)
        move = FacingBreath(
            pose, antennas, math.radians(body), math.radians(target[0]), math.radians(target[1]), duration
        )
        self.deps.movement_manager.queue_move(move)
        self.target = target
        self.busy_until = now + duration + SETTLE_S
        self.holding = True
        logger.info(
            "VOICE_LOOK turn worker=%s reason=%s heard=%s readings=%d from_head=%+.1f from_body=%+.1f "
            "head=%+.1f body=%+.1f",
            self.worker,
            reason,
            "-" if heard is None else f"{heard:+.1f}",
            readings,
            heading,
            body,
            *target,
        )

    async def step(self, state: dict[str, Any], now: float) -> None:
        """Pause for gestures/output, restore idle heading, and use fresh dominant speech evidence."""
        status = self.deps.movement_manager.get_status()
        if now < self.busy_until:
            return
        if status.get("queue_size") or not status.get("breathing_active"):
            self.readings.clear()
            self.holding = False
            return
        if state.get("speaking"):
            self.readings.clear()
            return
        if self.target is not None and not self.holding:
            self.queue(self.target, now, "restore")
            return
        doa = await asyncio.to_thread(_read_doa)
        if not self.running:
            return
        self.readings = [(t, bearing) for t, bearing in self.readings if now - t <= WINDOW_S]
        if doa is None or not doa[1]:
            return
        _, heading, body, _ = self.pose()
        self.readings.append((now, heading + 90 - math.degrees(doa[0])))
        values = [heading + angular_delta(bearing, heading) for _, bearing in self.readings]
        group = densest_group(values, GROUP_WIDTH_DEG)
        if len(group) < MIN_READINGS or len(group) / len(values) < MIN_DOMINANCE:
            return
        times = [t for (t, _), value in zip(self.readings, values, strict=True) if value in group]
        if max(times) - min(times) < MIN_EVIDENCE_S:
            return
        bearing = statistics.median(group)
        target = plan_turn(bearing, body)
        if abs(angular_delta(target[0], heading)) > TURN_IF_OFF_BY_DEG or abs(target[1] - body) > TURN_IF_OFF_BY_DEG:
            self.queue(target, now, "voice", bearing, len(group))
        self.readings.clear()

    async def start(self) -> dict[str, Any]:
        """Start the worker if it is not running and reply at once."""
        if self.task is not None and not self.task.done():
            if self.running:
                logger.info("VOICE_LOOK request worker=%s enabled=true result=already_on", self.worker)
                return {"enabled": True, "turning_to_voices": True}
            await asyncio.wait_for(asyncio.shield(self.task), timeout=3)  # a stopping worker exits first
        self.running = True
        self.task = asyncio.create_task(self.run())
        logger.info("VOICE_LOOK request worker=%s enabled=true result=started", self.worker)
        return {"enabled": True, "turning_to_voices": True}

    async def stop(self) -> dict[str, Any]:
        """Stop the worker and wait briefly for it to exit."""
        task = self.task
        was_on = task is not None and not task.done()
        self.running = False
        if task is not None and was_on:
            await asyncio.wait_for(asyncio.shield(task), timeout=3)
        result = "stopped" if was_on else "already_off"
        logger.info("VOICE_LOOK request worker=%s enabled=false result=%s", self.worker, result)
        return {"enabled": False, "turning_to_voices": False}

    async def run(self) -> None:
        """The worker loop; cancellation (app shutdown) always cleans up."""
        logger.info("VOICE_LOOK on worker=%s", self.worker)
        ended = "stopped"
        try:
            while self.running:
                state = {"speaking": bool(getattr(self.deps.movement_manager, "_is_speaking", False))}
                try:
                    await self.step(state, time.monotonic())
                except (OSError, ValueError, TimeoutError) as error:
                    logger.warning("VOICE_LOOK poll worker=%s error=%s", self.worker, type(error).__name__)
                await asyncio.sleep(POLL_S)
        except asyncio.CancelledError:
            ended = "cancelled"  # app shutdown or tool reload
            raise
        finally:
            self.running = False
            logger.info("VOICE_LOOK off worker=%s reason=%s", self.worker, ended)


class VoiceLook(Tool):  # type: ignore[misc]
    """Start or stop turning toward whoever is speaking; replies immediately."""

    name = "voice_look"
    description = (
        "Turns the robot's head and body toward whoever is talking, using the direction their voice comes "
        "from (microphones, not the camera; it works when the person is out of view). At the start of every "
        "conversation, call this once with no arguments to turn it on, unless the user has asked you not to; "
        "there is no need to mention that. Later, use it when the user wants the robot to stop or resume "
        "turning toward voices, for example 'turn to whoever is talking', 'turn round when I speak', 'stop "
        "turning every time someone talks' or 'keep your head still', and briefly confirm the new state. For "
        "following a face with the camera, use head_tracking instead. Replies at once."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "description": "true (default) to turn toward whoever is speaking; false to stop and keep the "
                "head where it is.",
            }
        },
        "required": [],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Start or stop the worker; never wait for it to finish."""
        enabled = kwargs.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        store = vars(deps.movement_manager)
        owner = store.get("_stock_voice_follower")
        if not isinstance(owner, StockFollower):
            if owner is not None:  # a worker from before a tool reload: end its loop before replacing it
                logger.info("VOICE_LOOK replacing worker from before a tool reload")
                owner.running = False
                old_task = getattr(owner, "task", None)
                if old_task is not None and not old_task.done():
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(asyncio.shield(old_task), timeout=3)
            owner = store["_stock_voice_follower"] = StockFollower(deps)
        return await (owner.start() if enabled else owner.stop())
