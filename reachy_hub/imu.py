"""Detect taps/knocks on the head from the IMU accelerometer, with strength and direction.

A tap is a reading whose acceleration vector moves more than ``threshold``
m/s^2 away from its recent normal (per-axis median of the last ~1 s of quiet
readings). The vector change, not the magnitude change, so sideways pushes count.
After a tap, further spikes are ignored for ``refractory_s`` so one knock counts once.
Tuned on real recordings (2026-10-13): hard taps gave 4-14 m/s^2; the 30 s
recording with the conversation app moving the head gave exactly its 3 taps.

Direction is the sideways part of the jolt (x/y) in the head sensor's own axes:
0 deg = sensor +x, 90 deg = sensor +y. Not yet calibrated to the robot's front.

Usage:
    detector = TapDetector()
    tap = detector.feed(time_s, imu["accelerometer"])  # None, or Tap(strength, direction_deg)
"""

import math
from collections import deque
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class Tap:
    """One detected tap: change from normal in m/s^2, and sideways direction in sensor degrees."""

    strength: float
    direction_deg: float


class TapDetector:
    """Turns a stream of accelerometer readings into taps."""

    def __init__(
        self, threshold: float = 2.0, refractory_s: float = 0.5, window: int = 45, min_baseline: int = 10
    ) -> None:
        """Create a detector.

        Args:
            threshold: Change from normal (m/s^2) that counts as a tap.
            refractory_s: Seconds after a tap during which spikes are ignored.
            window: Number of quiet readings that define "normal" (~1 s at 45/s).
            min_baseline: Readings needed before detection starts.
        """
        self._threshold = threshold
        self._refractory_s = refractory_s
        self._min_baseline = min_baseline
        self._quiet: deque[tuple[float, float, float]] = deque(maxlen=window)
        self._ignore_until = -math.inf

    def feed(self, time_s: float, accelerometer: list[float]) -> Tap | None:
        """Add one reading.

        Args:
            time_s: Reading time in seconds (any fixed origin).
            accelerometer: [x, y, z] in m/s^2.

        Returns:
            A Tap if this reading starts one, else None.
        """
        x, y, z = accelerometer
        if len(self._quiet) < self._min_baseline:
            self._quiet.append((x, y, z))
            return None
        normal = [median(axis) for axis in zip(*self._quiet, strict=True)]
        change = math.hypot(x - normal[0], y - normal[1], z - normal[2])  # vector change: catches sideways pushes
        if change <= self._threshold:
            self._quiet.append((x, y, z))
            return None
        if time_s < self._ignore_until:
            return None
        self._ignore_until = time_s + self._refractory_s
        direction = math.degrees(math.atan2(y - normal[1], x - normal[0]))
        return Tap(strength=round(change, 2), direction_deg=round(direction, 0))
