"""Capture the robot's pose and move between poses smoothly, for any tool that needs to turn the body or head.

Yaw is interpolated as a plain angle, never as a rotation matrix: a matrix cannot tell -190 from +170 degrees and
takes the short way round, which for the body and head together is a violent swing against the cable limits.
Moves are queued through the app's movement manager (``movement_manager.queue_move``), which stays the only
writer to the motors.

Usage:
    start = motion.snapshot(deps.reachy_mini)
    target = motion.facing(start, heading_deg=-160, body_deg=-125, pitch_deg=0)
    deps.movement_manager.queue_move(motion.PoseMove(start, target))
"""

import math
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import numpy.typing as npt
from reachy_mini.motion.move import Move  # type: ignore[import-untyped]
from reachy_mini.utils import create_head_pose  # type: ignore[import-untyped]

HEAD_SPEED_DEG_S = 40.0  # slowest head yaw speed a move may need, from the voice_look turns
BODY_SPEED_DEG_S = 35.0
MIN_MOVE_S = 1.0


def angular_delta(target: float, origin: float) -> float:
    """Shortest signed angle from ``origin`` to ``target``, in degrees."""
    return (target - origin + 180.0) % 360.0 - 180.0


@dataclass(frozen=True)
class PoseSnapshot:
    """The robot's pose at one moment. Angles in radians, position in metres.

    ``heading`` is the head's yaw from the base, unwrapped to lie next to the body yaw, so it can be
    interpolated as a number (it may be beyond +-180 degrees when the body has turned a long way).
    """

    x: float
    y: float
    z: float
    roll: float
    pitch: float
    heading: float
    body: float
    antennas: tuple[float, float]


def snapshot(reachy_mini: Any) -> PoseSnapshot:
    """Read the current pose with the SDK's public sensing calls."""
    joints, antennas = reachy_mini.get_current_joint_positions()
    return from_pose(
        reachy_mini.get_current_head_pose(), float(joints[0]), (float(antennas[0]), float(antennas[1]))
    )


def from_pose(pose: npt.NDArray[np.float64], body: float, antennas: tuple[float, float]) -> PoseSnapshot:
    """A snapshot from a head pose matrix, body yaw (radians) and antenna angles, when no robot is to hand."""
    raw_yaw = math.degrees(math.atan2(pose[1, 0], pose[0, 0]))
    return PoseSnapshot(
        x=float(pose[0, 3]),
        y=float(pose[1, 3]),
        z=float(pose[2, 3]),
        roll=math.atan2(pose[2, 1], pose[2, 2]),
        pitch=math.asin(max(-1.0, min(1.0, -float(pose[2, 0])))),
        heading=body + math.radians(angular_delta(raw_yaw, math.degrees(body))),
        body=body,
        antennas=antennas,
    )


def facing(start: PoseSnapshot, heading_deg: float, body_deg: float, pitch_deg: float) -> PoseSnapshot:
    """``start`` turned to a new heading, body yaw and pitch (degrees); everything else is kept."""
    return replace(
        start, heading=math.radians(heading_deg), body=math.radians(body_deg), pitch=math.radians(pitch_deg)
    )


def travel_seconds(head_deg: float, body_deg: float, min_s: float = MIN_MOVE_S) -> float:
    """Seconds needed to turn the head and body by these angles (either sign) within their speed limits."""
    return max(min_s, abs(head_deg) / HEAD_SPEED_DEG_S, abs(body_deg) / BODY_SPEED_DEG_S)


def move_duration(start: PoseSnapshot, target: PoseSnapshot, min_s: float = MIN_MOVE_S) -> float:
    """Seconds a move between two poses needs so neither the head nor the body turns too fast."""
    return travel_seconds(
        math.degrees(target.heading - start.heading), math.degrees(target.body - start.body), min_s
    )


class PoseMove(Move):  # type: ignore[misc]
    """A queueable move from one pose to another, eased with minimum jerk, interpolating every component."""

    def __init__(self, start: PoseSnapshot, target: PoseSnapshot, duration: float | None = None) -> None:
        """Set up the move.

        Args:
            start: Where the move begins (normally ``snapshot`` of the robot, or the last commanded pose).
            target: Where it ends.
            duration: Seconds; computed from the angles with ``move_duration`` when not given.

        Raises:
            ValueError: ``duration`` is zero or negative.
        """
        self._start = start
        self._target = target
        self._duration = move_duration(start, target) if duration is None else duration
        if self._duration <= 0:
            raise ValueError(f"A move needs a positive duration, got {self._duration}")

    @property
    def duration(self) -> float:
        """Seconds the move takes."""
        return self._duration

    def evaluate(self, t: float) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], float]:
        """The pose at time ``t`` seconds: head matrix, antennas (radians) and body yaw (radians)."""
        progress = max(0.0, min(1.0, t / self._duration))
        eased = progress**3 * (10 - 15 * progress + 6 * progress**2)
        a, b = self._start, self._target

        def mix(start: float, end: float) -> float:
            return start + eased * (end - start)

        head = create_head_pose(
            x=mix(a.x, b.x),
            y=mix(a.y, b.y),
            z=mix(a.z, b.z),
            roll=mix(a.roll, b.roll),
            pitch=mix(a.pitch, b.pitch),
            yaw=mix(a.heading, b.heading),
            degrees=False,
        )
        antennas = np.array([mix(a.antennas[0], b.antennas[0]), mix(a.antennas[1], b.antennas[1])])
        return head, antennas, mix(a.body, b.body)
