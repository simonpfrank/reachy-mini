"""reachy_lib.motion: capture a pose and move between poses by interpolating angles, never matrices."""

import math
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from reachy_mini.utils import create_head_pose

TOOLS = Path(__file__).resolve().parents[2] / "robot_tools"


@pytest.fixture
def motion(monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    sys.modules.pop("reachy_lib.motion", None)
    sys.modules.pop("reachy_lib", None)
    from reachy_lib import motion as module

    return module


def fake_robot(roll=0.0, pitch=0.0, yaw=0.0, body=0.0, antennas=(0.1, -0.1)):
    pose = create_head_pose(0, 0, 0.01, roll=roll, pitch=pitch, yaw=yaw)
    joints = [math.radians(body), 0, 0, 0, 0, 0, 0]
    return types.SimpleNamespace(
        get_current_head_pose=lambda: pose, get_current_joint_positions=lambda: (joints, list(antennas))
    )


def heading_of(head) -> float:
    return math.degrees(math.atan2(head[1, 0], head[0, 0]))


def test_angular_delta_is_the_shortest_signed_angle(motion):
    assert motion.angular_delta(190, 0) == pytest.approx(-170)
    assert motion.angular_delta(-190, 0) == pytest.approx(170)
    assert motion.angular_delta(30, 10) == pytest.approx(20)


def test_snapshot_reads_the_whole_pose(motion):
    s = motion.snapshot(fake_robot(roll=12, pitch=-8, yaw=30, body=20))
    assert (math.degrees(s.heading), math.degrees(s.pitch), math.degrees(s.roll)) == pytest.approx((30, -8, 12))
    assert math.degrees(s.body) == pytest.approx(20)
    assert s.z == pytest.approx(0.01) and s.antennas == (0.1, -0.1)


def test_snapshot_heading_is_unwrapped_next_to_the_body(motion):
    s = motion.snapshot(fake_robot(yaw=170, body=-100))
    assert math.degrees(s.heading) == pytest.approx(-190)


def test_facing_changes_only_heading_body_and_pitch(motion):
    start = motion.snapshot(fake_robot(roll=12, pitch=-8, yaw=30, body=20))
    target = motion.facing(start, heading_deg=-160, body_deg=-125, pitch_deg=0)
    assert (math.degrees(target.heading), math.degrees(target.body), math.degrees(target.pitch)) == pytest.approx(
        (-160, -125, 0)
    )
    assert target.roll == start.roll and target.z == start.z and target.antennas == start.antennas


def test_the_move_starts_at_the_start_and_ends_exactly_at_the_target(motion):
    start = motion.snapshot(fake_robot(roll=12, pitch=-8, yaw=30, body=20))
    target = motion.facing(start, heading_deg=-160, body_deg=-125, pitch_deg=5)
    move = motion.PoseMove(start, target, duration=2.0)
    head, _, body = move.evaluate(0.0)
    assert heading_of(head) == pytest.approx(30) and math.degrees(body) == pytest.approx(20)
    head, antennas, body = move.evaluate(2.0)
    assert heading_of(head) == pytest.approx(-160) and math.degrees(body) == pytest.approx(-125)
    assert np.allclose(head, create_head_pose(0, 0, 0.01, roll=12, pitch=5, yaw=-160))
    assert tuple(antennas) == (0.1, -0.1)


def test_a_long_turn_goes_the_long_way_in_small_steps(motion):
    start = motion.snapshot(fake_robot(yaw=-170, body=-125))
    target = motion.facing(start, heading_deg=170, body_deg=140, pitch_deg=0)
    move = motion.PoseMove(start, target, duration=4.0)
    headings = [heading_of(move.evaluate(4.0 * i / 100)[0]) for i in range(101)]
    steps = np.diff(headings)
    assert np.all(steps >= -1e-9) and steps.max() < 15  # never takes the short way across +-180
    assert headings[50] == pytest.approx(0, abs=1)


def test_every_component_stays_between_its_start_and_target(motion):
    start = motion.snapshot(fake_robot(roll=12, pitch=-8, yaw=30, body=20))
    target = motion.facing(start, heading_deg=-160, body_deg=-125, pitch_deg=5)
    move = motion.PoseMove(start, target, duration=2.0)
    for i in range(101):
        _, _, body = move.evaluate(2.0 * i / 100)
        assert math.radians(-125) - 1e-9 <= body <= math.radians(20) + 1e-9


def test_duration_grows_with_the_angle_and_has_a_floor(motion):
    start = motion.snapshot(fake_robot(yaw=0, body=0))
    far = motion.facing(start, heading_deg=-195, body_deg=-125, pitch_deg=0)
    near = motion.facing(start, heading_deg=5, body_deg=0, pitch_deg=0)
    assert motion.move_duration(start, far) == pytest.approx(1.875 * 195 / 40)
    assert motion.move_duration(start, near) == 1.0


def test_travel_seconds_obeys_the_speed_limits_in_either_direction(motion):
    assert motion.travel_seconds(80, 0) == pytest.approx(3.75)  # 80 deg at a 40 deg/s peak: 1.875 x 80 / 40
    assert motion.travel_seconds(0, -70) == pytest.approx(3.75)  # 70 deg at a 35 deg/s peak: 1.875 x 70 / 35
    assert motion.travel_seconds(10, 10) == 1.0  # the floor
    assert motion.travel_seconds(1, 1, min_s=0.2) == 0.2


def test_from_pose_gives_the_same_snapshot_as_reading_the_robot(motion):
    robot = fake_robot(roll=12, pitch=-8, yaw=30, body=20)
    joints, antennas = robot.get_current_joint_positions()
    built = motion.from_pose(robot.get_current_head_pose(), float(joints[0]), (antennas[0], antennas[1]))
    assert built == motion.snapshot(robot)


def test_the_default_duration_is_the_computed_one(motion):
    start = motion.snapshot(fake_robot())
    target = motion.facing(start, heading_deg=-195, body_deg=-125, pitch_deg=0)
    assert motion.PoseMove(start, target).duration == motion.move_duration(start, target)


def peak_speeds(move) -> tuple[float, float]:
    """Highest body and head yaw speed (deg/s) anywhere along the move, read back from what it commands."""
    moments = np.linspace(0, move.duration, 400)
    samples = [move.evaluate(float(t)) for t in moments]
    body = np.degrees([sample[2] for sample in samples])
    head = np.degrees(np.unwrap([math.atan2(s[0][1, 0], s[0][0, 0]) for s in samples]))
    step = moments[1] - moments[0]
    return float(np.abs(np.diff(body)).max() / step), float(np.abs(np.diff(head)).max() / step)


@pytest.mark.parametrize(
    ("start_heading", "start_body", "heading", "body"),
    [(0, 0, -195, -125), (-170, -125, 170, 140), (-75, -110, -20, -55), (-90, -125, -140, -125), (10, 5, 40, 20)],
)
def test_no_move_goes_faster_than_the_speed_limits_at_any_instant(motion, start_heading, start_body, heading, body):
    start = motion.snapshot(fake_robot(yaw=start_heading, body=start_body))
    move = motion.PoseMove(start, motion.facing(start, heading_deg=heading, body_deg=body, pitch_deg=0))
    body_peak, head_peak = peak_speeds(move)
    assert body_peak <= motion.BODY_SPEED_DEG_S * 1.01 and head_peak <= motion.HEAD_SPEED_DEG_S * 1.01
