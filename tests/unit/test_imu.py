import json
from pathlib import Path

from reachy_hub.imu import Tap, TapDetector

DATA = Path(__file__).parent.parent / "data"
GRAVITY = [0.0, 0.0, 9.75]


def _run(samples: list[tuple[float, list[float]]]) -> list[tuple[float, Tap]]:
    detector = TapDetector()
    taps = []
    for t, acc in samples:
        tap = detector.feed(t, acc)
        if tap is not None:
            taps.append((t, tap))
    return taps


def _still(seconds: float, start: float = 0.0) -> list[tuple[float, list[float]]]:
    return [(start + i / 45, GRAVITY) for i in range(int(seconds * 45))]


def test_three_real_taps_are_found_once_each() -> None:
    rows = json.loads((DATA / "imu_three_taps.json").read_text())
    t0 = rows[0]["t"]
    taps = _run([(r["t"] - t0, r["acc"]) for r in rows])
    assert [round(t) for t, _ in taps] == [7, 15, 21]
    assert all(tap.strength > 2.0 and -180 <= tap.direction_deg <= 180 for _, tap in taps)


def test_still_head_gives_no_taps() -> None:
    samples = [(i / 45, [0.0, 0.05 * (i % 3), 9.75]) for i in range(450)]
    assert _run(samples) == []


def test_spikes_within_half_a_second_count_as_one_tap() -> None:
    samples = _still(2.0) + [(2.0, [0.0, 0.0, 14.0]), (2.2, [0.0, 0.0, 4.0])] + _still(1.0, start=2.3)
    assert len(_run(samples)) == 1


def test_needs_a_baseline_before_detecting() -> None:
    assert _run([(0.0, [0.0, 0.0, 20.0])]) == []


def test_tap_direction_is_the_sideways_push_in_sensor_axes() -> None:
    push_x = _run(_still(2.0) + [(2.0, [4.0, 0.0, 9.75])])
    push_y = _run(_still(2.0) + [(2.0, [0.0, 4.0, 9.75])])
    assert (push_x[0][1].direction_deg, push_y[0][1].direction_deg) == (0.0, 90.0)
