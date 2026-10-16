"""Voice following owned by the stock app's background-tool manager.

Started by a normal tool call (the profile greeting asks for it at session start). Uses the public
movement queue/status methods, SDK sensing and BreathingMove's Move contract, and reads the movement
manager's speaking flag to ignore the robot's own voice. No relay, app hooks, import-time workers,
direct daemon motor commands or installed-code changes.
"""

import asyncio
import json
import logging
import math
import statistics
import time
import urllib.request
import uuid
from typing import Any

from reachy_mini.utils import create_head_pose  # type: ignore[import-untyped]
from reachy_mini_conversation_app.moves import BreathingMove
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

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


def angular_delta(target: float, origin: float) -> float:
    """Shortest signed angle in degrees."""
    return (target - origin + 180.0) % 360.0 - 180.0


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
    return max(MOVE_S, abs(target_heading - unwrapped_heading) / 40.0, abs(target_body - body) / 35.0)


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
        """Use the base constructor's public signature; keep all custom interpolation state here."""
        super().__init__(pose, antennas, duration)
        self._pose = pose.copy()
        self._antennas = antennas
        self._seconds = duration
        self._from_body, self._to_body = start_body, body
        raw_yaw = math.atan2(pose[1, 0], pose[0, 0])
        self._from_yaw = start_body + math.radians(angular_delta(math.degrees(raw_yaw), math.degrees(start_body)))
        self._to_yaw = heading
        self._from_pitch = math.asin(max(-1.0, min(1.0, -float(pose[2, 0]))))
        self._from_roll = math.atan2(pose[2, 1], pose[2, 2])

    def evaluate(self, t: float) -> tuple[Any, Any, float]:
        """Implement the SDK Move contract without reading or changing base-class internals."""
        progress = max(0.0, min(1.0, t / self._seconds))
        eased = progress**3 * (10 - 15 * progress + 6 * progress**2)
        rest = 1 - eased
        z = float(self._pose[2, 3]) * rest
        if progress >= 1:
            z += 0.003 * math.sin(2 * math.pi * 0.1 * (t - self._seconds))
        head = create_head_pose(
            x=float(self._pose[0, 3]) * rest,
            y=float(self._pose[1, 3]) * rest,
            z=z,
            roll=self._from_roll * rest,
            pitch=self._from_pitch * rest,
            yaw=self._from_yaw + eased * (self._to_yaw - self._from_yaw),
            degrees=False,
        )
        return head, self._antennas, self._from_body + eased * (self._to_body - self._from_body)


class StockFollower:
    """One cancellable coroutine, owned by BackgroundToolManager rather than a detached thread."""

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

    def queue(self, target: tuple[float, float], now: float) -> None:
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
        logger.info("VOICE_LOOK turn worker=%s head=%+.1f body=%+.1f", self.worker, *target)

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
            self.queue(self.target, now)
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
            self.queue(target, now)
        self.readings.clear()

    async def run(self) -> dict[str, Any]:
        """Awaited directly by the app's cancellable tool task; cancellation always cleans up."""
        if self.task is not None and not self.task.done() and (not self.running or self.task.cancelling()):
            await asyncio.wait_for(asyncio.shield(self.task), timeout=3)
        if self.running:
            return {"enabled": True, "running": True, "worker": self.worker}
        self.task = asyncio.current_task()
        self.running = True
        logger.info("VOICE_LOOK on worker=%s", self.worker)
        try:
            while self.running:
                state = {"speaking": bool(getattr(self.deps.movement_manager, "_is_speaking", False))}
                try:
                    await self.step(state, time.monotonic())
                except (OSError, ValueError, TimeoutError) as error:
                    logger.warning("VOICE_LOOK poll worker=%s error=%s", self.worker, type(error).__name__)
                await asyncio.sleep(POLL_S)
        finally:
            self.running = False
            logger.info("VOICE_LOOK off worker=%s", self.worker)
        return {"enabled": False, "running": False, "worker": self.worker}


class VoiceLook(Tool):  # type: ignore[misc]
    """Enable/disable speaker following through the app's managed background-tool task."""

    name = "voice_look"
    needs_response = False
    description = (
        "Follow the speaker with head and body. Following starts automatically with the conversation. "
        "enabled=false stops following; enabled=true resumes. The enabled task runs in the background until "
        "stopped; do not call it repeatedly or wait for completion before continuing a conversation."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"enabled": {"type": "boolean"}},
        "required": ["enabled"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """The app manager owns the coroutine lifetime, including backend restart and shutdown."""
        enabled = kwargs.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        manager = deps.movement_manager
        owner = vars(manager).setdefault("_stock_voice_follower", StockFollower(deps))
        if not enabled:
            owner.running = False
            if owner.task is not None and not owner.task.done():
                await asyncio.wait_for(asyncio.shield(owner.task), timeout=3)
            return {"enabled": False, "running": False}
        return await owner.run()  # type: ignore[no-any-return]
