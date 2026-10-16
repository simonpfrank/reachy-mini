"""Decide when and how far to turn the head toward a NEW speech source (roadmap 3a, experimental second version).

Pure logic: no robot code. Feed it sound samples and the head's current turn; it returns a turn decision
or None. Sound direction scale (mic array): 0 = left, 90 = straight ahead (or behind), 180 = right.
Head yaw: positive = left, relative to the body.

Why "new" and not "strongest": the chip's angle is fresh only while its speech flag is on (otherwise it repeats the
last value), and the flag is intermittent. A TV is flagged all the time, a person only in bursts, so the strongest
source is always the TV. Instead each flagged reading is turned into a bearing from the body (head turn + offset, so
head moves do not smear the picture) and counted per direction:
- Ambient: how often that direction was flagged over the last ``ambient_s`` seconds (the standing TV).
- New: a direction flagged at least ``min_new`` times in the last ``evidence_s`` seconds, at three times its ambient
  rate. Intermittent speech still qualifies because readings are counted over seconds, not frames.
- After a turn the head stays put: leaving it needs twice the evidence for ``lock_s`` seconds.
- Head only, capped at ``max_head_deg``. Cooldown after every decision.

Usage:
    tracker = VoiceTracker()
    decision = tracker.feed(SoundSample(t, angle_deg, speech), head_deg)
    print(tracker.note)  # why it did or did not turn
"""

import statistics
from collections import deque
from dataclasses import dataclass

FRONT_DEG = 90.0


@dataclass(frozen=True)
class SoundSample:
    """One reading of the mic array. ``angle_deg`` is None when there is no reading."""

    t: float
    angle_deg: float | None
    speech: bool


@dataclass(frozen=True)
class TurnDecision:
    """A decision to turn the head. ``offset_deg``: positive = the source is to the left."""

    t: float
    source_deg: float
    offset_deg: float
    target_head_deg: float
    clamped: bool


def _densest_cluster(values: list[float], width: float) -> list[float]:
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


class VoiceTracker:
    """Turns a stream of sound samples into occasional head-turn decisions."""

    def __init__(
        self,
        evidence_s: float = 2.0,
        ambient_s: float = 30.0,
        min_new: int = 4,
        new_factor: float = 3.0,
        width_deg: float = 40.0,
        deadband_deg: float = 8.0,
        cooldown_s: float = 3.0,
        lock_s: float = 10.0,
        max_head_deg: float = 35.0,
    ) -> None:
        """Create a tracker.

        Args:
            evidence_s: Seconds of recent flagged readings that count as evidence for a new source.
            ambient_s: Seconds of history that define what is already there (TV, fan).
            min_new: Fewest flagged readings in the evidence window (20 Hz, so 10 is about half a second).
            new_factor: How many times its ambient rate a direction must exceed to count as new.
            width_deg: Width of a direction (readings within this belong to one source).
            deadband_deg: Ignore turns smaller than this (already facing the source).
            cooldown_s: Seconds after a decision before the next one is allowed.
            lock_s: Seconds after a turn during which leaving needs twice the evidence.
            max_head_deg: Head-only turn limit either side of the body.
        """
        self._evidence_s = evidence_s
        self._ambient_s = ambient_s
        self._min_new = min_new
        self._factor = new_factor
        self._width = width_deg
        self._deadband = deadband_deg
        self._cooldown_s = cooldown_s
        self._lock_s = lock_s
        self._max_head = max_head_deg
        self._readings: deque[tuple[float, float]] = deque()  # (time, bearing from body, left +)
        self._first_t: float | None = None
        self._next_allowed = float("-inf")
        self._locked_until = float("-inf")
        self.note = "waiting"

    def feed(self, sample: SoundSample, head_deg: float) -> TurnDecision | None:
        """Add one sample.

        Args:
            sample: The latest sound reading.
            head_deg: Where the head points now, degrees left of the body (negative = right).

        Returns:
            A TurnDecision when a new speech source needs a turn, else None.
        """
        if self._first_t is None:
            self._first_t = sample.t
        if sample.speech and sample.angle_deg is not None:
            self._readings.append((sample.t, head_deg + FRONT_DEG - sample.angle_deg))
        while self._readings and sample.t - self._readings[0][0] > self._ambient_s:
            self._readings.popleft()
        if sample.t - self._first_t < self._evidence_s:
            self.note = "warming up"
            return None
        recent = [b for t, b in self._readings if sample.t - t <= self._evidence_s]
        group = _densest_cluster(recent, self._width)
        needed = self._min_new * (2 if sample.t < self._locked_until else 1)
        if len(group) < needed:
            self.note = f"flagged {len(recent)} in {self._evidence_s:.0f}s, best group {len(group)} (need {needed})"
            return None
        bearing = statistics.median(group)
        older = [b for t, b in self._readings if sample.t - t > self._evidence_s]
        standing = [b for b in older if abs(b - bearing) <= self._width]
        ambient_rate = len(standing) / max(1.0, min(self._ambient_s, sample.t - self._first_t) - self._evidence_s)
        recent_rate = len(group) / self._evidence_s
        self.note = f"group of {len(group)} at {bearing:+.0f} deg: {recent_rate:.1f}/s, standing {ambient_rate:.1f}/s"
        if recent_rate < self._factor * ambient_rate or sample.t < self._next_allowed:
            return None
        target = max(-self._max_head, min(self._max_head, bearing))
        if abs(target - head_deg) < self._deadband:
            return None
        self._next_allowed = sample.t + self._cooldown_s
        self._locked_until = sample.t + self._lock_s
        offset = bearing - head_deg
        return TurnDecision(sample.t, FRONT_DEG - offset, offset, target, clamped=target != bearing)
