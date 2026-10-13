"""Normalise raw telemetry messages into two plain shapes.

``Event`` is something that happened (e.g. an app pushed ``conversation.turn``).
``RobotState`` is a snapshot of the robot's body from the daemon, in degrees.

Usage:
    event = event_from_rpc(json.loads(raw), datetime.now(UTC))
    state = robot_state_from_full(json.loads(raw_state))
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Event:
    """Something that happened, from one source.

    Attributes:
        time: When the hub received it.
        source: Where it came from: "app", "daemon" or "system".
        kind: What happened, e.g. "conversation.turn".
        data: Event details as sent by the source.
    """

    time: datetime
    source: str
    kind: str
    data: Mapping[str, Any]


@dataclass(frozen=True)
class ImuReading:
    """One IMU reading in readable units.

    ``tilt_deg`` is the angle between the sensor's z axis and vertical (0 = level),
    ``tilt_dir_deg`` which way it leans in sensor axes (0 = +x, 90 = +y),
    ``motion_dps`` the rotation speed in degrees/second, ``accel`` the acceleration
    magnitude in m/s^2 (about 9.8 when still).
    """

    accel_xyz: tuple[float, float, float]
    gyro_dps_xyz: tuple[float, float, float]
    tilt_deg: float
    tilt_dir_deg: float
    motion_dps: float
    accel: float


def imu_reading(imu: object) -> ImuReading | None:
    """Convert the daemon's ``imu`` dict to an ImuReading, or None if it is missing or malformed.

    Args:
        imu: The ``imu`` field of a daemon state payload.

    Returns:
        The reading, or None.
    """
    if not isinstance(imu, dict):
        return None
    acc, gyro = imu.get("accelerometer"), imu.get("gyroscope")
    if not (isinstance(acc, list) and isinstance(gyro, list) and len(acc) == 3 and len(gyro) == 3):
        return None
    accel = math.hypot(*acc)
    gyro_dps = tuple(round(math.degrees(g), 1) for g in gyro)
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, acc[2] / accel)))) if accel else 0.0
    return ImuReading(
        accel_xyz=(round(acc[0], 2), round(acc[1], 2), round(acc[2], 2)),
        gyro_dps_xyz=(gyro_dps[0], gyro_dps[1], gyro_dps[2]),
        tilt_deg=round(tilt, 1),
        tilt_dir_deg=round(math.degrees(math.atan2(acc[1], acc[0])), 0),
        motion_dps=round(math.degrees(math.hypot(*gyro)), 1),
        accel=round(accel, 2),
    )


@dataclass(frozen=True)
class RobotState:
    """The robot's body at one moment. Angles in degrees; None when not reported.

    ``sound_dir_deg`` is degrees from straight ahead, positive to the robot's left.
    """

    timestamp: str
    motor_mode: str | None
    head_roll_deg: float | None
    head_pitch_deg: float | None
    head_yaw_deg: float | None
    body_yaw_deg: float | None
    sound_dir_deg: float | None
    speech_detected: bool | None
    imu_temp_c: float | None
    imu_tilt_deg: float | None
    imu_tilt_dir_deg: float | None
    imu_motion_dps: float | None
    imu_accel: float | None


def event_from_rpc(message: object, now: datetime) -> Event | None:
    """Turn a JSON-RPC notification from an app into an Event.

    Args:
        message: Decoded JSON message from the app's ``/rpc`` WebSocket.
        now: Receive time to stamp on the event.

    Returns:
        The Event, or None for replies and anything that is not a notification.
    """
    if not isinstance(message, dict) or not isinstance(message.get("method"), str):
        return None
    params = message.get("params")
    return Event(now, "app", message["method"], params if isinstance(params, dict) else {})


def _deg(value: Any) -> float | None:
    return round(math.degrees(value), 1) if isinstance(value, int | float) else None


def robot_state_from_full(payload: Mapping[str, Any]) -> RobotState:
    """Build a RobotState from the daemon's ``/api/state/full`` payload.

    Args:
        payload: Decoded JSON from ``/api/state/full`` or ``/api/state/ws/full``.

    Returns:
        RobotState with angles converted from radians to degrees.
    """
    pose = payload.get("head_pose") or {}
    doa = payload.get("doa") or {}
    imu = payload.get("imu") or {}
    angle = doa.get("angle")
    reading = imu_reading(payload.get("imu"))
    return RobotState(
        timestamp=str(payload.get("timestamp", "")),
        motor_mode=payload.get("control_mode"),
        head_roll_deg=_deg(pose.get("roll")),
        head_pitch_deg=_deg(pose.get("pitch")),
        head_yaw_deg=_deg(pose.get("yaw")),
        body_yaw_deg=_deg(payload.get("body_yaw")),
        sound_dir_deg=_deg(math.pi / 2 - angle) if isinstance(angle, int | float) else None,
        speech_detected=doa.get("speech_detected"),
        imu_temp_c=imu.get("temperature"),
        imu_tilt_deg=reading.tilt_deg if reading else None,
        imu_tilt_dir_deg=reading.tilt_dir_deg if reading else None,
        imu_motion_dps=reading.motion_dps if reading else None,
        imu_accel=reading.accel if reading else None,
    )
