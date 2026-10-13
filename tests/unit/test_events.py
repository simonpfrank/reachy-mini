import json
import math
from datetime import UTC, datetime
from pathlib import Path

from reachy_hub.events import Event, event_from_rpc, robot_state_from_full

DATA = Path(__file__).parent.parent / "data"
NOW = datetime(2026, 10, 13, 16, 0, 0, tzinfo=UTC)


def test_rpc_notification_becomes_app_event() -> None:
    msg = {"jsonrpc": "2.0", "method": "conversation.turn", "params": {"state": "speaking"}}
    assert event_from_rpc(msg, NOW) == Event(NOW, "app", "conversation.turn", {"state": "speaking"})


def test_rpc_reply_is_not_an_event() -> None:
    assert event_from_rpc({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}, NOW) is None


def test_rpc_notification_without_params_has_empty_data() -> None:
    event = event_from_rpc({"jsonrpc": "2.0", "method": "conversation.activity"}, NOW)
    assert event is not None and event.data == {}


def test_non_dict_rpc_message_is_ignored() -> None:
    assert event_from_rpc(["not", "a", "message"], NOW) is None


def test_robot_state_from_real_sample() -> None:
    payload = json.loads((DATA / "state_full.json").read_text())
    state = robot_state_from_full(payload)
    assert state.motor_mode == "enabled"
    assert state.head_pitch_deg == round(math.degrees(payload["head_pose"]["pitch"]), 1)
    assert state.speech_detected is False
    assert state.imu_temp_c == 52.0


def test_imu_gives_tilt_motion_and_acceleration() -> None:
    payload = json.loads((DATA / "state_full.json").read_text())
    ax, ay, az = payload["imu"]["accelerometer"]
    gx, gy, gz = payload["imu"]["gyroscope"]
    state = robot_state_from_full(payload)
    accel = math.sqrt(ax * ax + ay * ay + az * az)
    assert state.imu_accel == round(accel, 2)
    assert state.imu_tilt_deg == round(math.degrees(math.acos(az / accel)), 1)
    assert state.imu_motion_dps == round(math.degrees(math.sqrt(gx * gx + gy * gy + gz * gz)), 1)


def test_tilt_direction_is_where_the_head_leans_in_sensor_axes() -> None:
    lean_y = robot_state_from_full(
        {"control_mode": "enabled", "timestamp": "t", "imu": {"accelerometer": [0, 1.0, 9.76], "gyroscope": [0, 0, 0]}}
    )
    assert lean_y.imu_tilt_dir_deg == 90.0


def test_level_still_head_reads_zero_tilt_and_motion() -> None:
    state = robot_state_from_full(
        {"control_mode": "enabled", "timestamp": "t", "imu": {"accelerometer": [0, 0, 9.81], "gyroscope": [0, 0, 0]}}
    )
    assert (state.imu_tilt_deg, state.imu_motion_dps, state.imu_accel) == (0.0, 0.0, 9.81)


def test_sound_direction_is_degrees_from_front_left_positive() -> None:
    base = {"control_mode": "enabled", "timestamp": "t"}
    left = robot_state_from_full({**base, "doa": {"angle": 0.0, "speech_detected": True}})
    front = robot_state_from_full({**base, "doa": {"angle": math.pi / 2, "speech_detected": False}})
    right = robot_state_from_full({**base, "doa": {"angle": math.pi, "speech_detected": False}})
    assert (left.sound_dir_deg, front.sound_dir_deg, right.sound_dir_deg) == (90.0, 0.0, -90.0)


def test_missing_optional_fields_are_none() -> None:
    state = robot_state_from_full({"control_mode": "disabled", "timestamp": "t"})
    assert state.head_pitch_deg is None and state.sound_dir_deg is None and state.imu_temp_c is None
    assert state.imu_tilt_deg is None and state.imu_motion_dps is None and state.imu_accel is None
