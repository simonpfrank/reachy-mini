import json
import math
from pathlib import Path

from reachy_hub.track import frame_verdict, goto_body, sample_from_state

DATA = Path(__file__).parent.parent / "data"


def test_state_message_becomes_sample_and_head_position() -> None:
    state = json.loads((DATA / "state_full.json").read_text())
    sample, head_deg = sample_from_state(state, now=12.5)
    assert sample.t == 12.5
    assert sample.angle_deg == math.degrees(state["doa"]["angle"])
    assert sample.speech is state["doa"]["speech_detected"]
    assert head_deg == math.degrees(state["head_pose"]["yaw"]) - math.degrees(state["body_yaw"])


def test_state_without_sound_reading_gives_no_angle() -> None:
    sample, head_deg = sample_from_state({"head_pose": {"yaw": 0.1}, "body_yaw": 0.1}, now=1.0)
    assert sample.angle_deg is None and sample.speech is False
    assert head_deg == 0.0


def test_goto_body_turns_head_relative_to_the_body_and_keeps_the_body_still() -> None:
    body = goto_body(target_head_deg=30.0, body_yaw_deg=10.0, duration_s=1.5)
    assert body["duration"] == 1.5
    assert body["body_yaw"] == math.radians(10.0)
    assert body["head_pose"]["yaw"] == math.radians(40.0)  # heading from the base = body + head turn
    assert {k: body["head_pose"][k] for k in ("x", "y", "z", "roll", "pitch")} == dict.fromkeys("xyz", 0.0) | {
        "roll": 0.0,
        "pitch": 0.0,
    }


def test_frame_verdict_reading_follows_the_head() -> None:
    # same video source: reading 69 with the head near centre, 20 after the head turned 33 deg right
    assert frame_verdict(before_deg=69.0, after_deg=20.0, head_change_deg=-33.0) == "head-relative"


def test_frame_verdict_reading_unchanged_means_base_relative() -> None:
    assert frame_verdict(before_deg=69.0, after_deg=70.0, head_change_deg=-33.0) == "base-relative"


def test_frame_verdict_different_source_is_inconclusive() -> None:
    # Simon's voice at 122 before the turn, the video at 20 after: not the same source, so no verdict
    assert frame_verdict(before_deg=122.0, after_deg=20.0, head_change_deg=-33.0) == "inconclusive"


def test_frame_verdict_small_head_move_is_inconclusive() -> None:
    assert frame_verdict(before_deg=95.0, after_deg=92.0, head_change_deg=-5.0) == "inconclusive"


def test_frame_verdict_on_the_measured_recording() -> None:
    # tests/data/motion_live_track.json: head moved +25.8 deg, the video's reading moved +27.0 deg
    assert frame_verdict(before_deg=21.0, after_deg=48.0, head_change_deg=25.8) == "head-relative"
