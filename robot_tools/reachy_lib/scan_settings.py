"""The room scan's settings: code defaults, then scan.json in the state folder, then REACHY_SCAN_* variables.

Shared by the scan and by the tool that reports what it found, so both read the same settings the same way.
scan.json is read fresh every time (no restart); a bad file or value is refused with a message that names it. The two
tables in it, ``models`` and ``tiers``, are for ``reachy_lib.detection``.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from typing import Any

from .storage import state_dir


def _number(environ: Mapping[str, str], name: str, default: float) -> float:
    """A float setting; a value that is not a number is refused, naming the setting."""
    raw = environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a number, got {raw!r}") from error


SETTINGS_FILE = "scan.json"
SETTING_NAMES = (  # the keys scan.json may hold: the REACHY_SCAN_* names without the prefix, lower case
    "overlap",
    "hfov_deg",
    "body_yaw_min_deg",
    "body_yaw_max_deg",
    "head_yaw_min_deg",
    "head_yaw_max_deg",
    "pitch_deg",
    "settle_s",
    "crop",
    "confidence",
    "nms_iou",
    "analysis_threads",
    "stale_after_s",
    "merge_tolerance_deg",
    "merge_overlap",
)


TABLE_NAMES = ("models", "tiers")  # the two entries that hold tables, not single values; see reachy_lib.detection


def _read_file() -> dict[str, Any]:
    """scan.json from the state folder, read fresh each time: empty if there is no file, refused if it is wrong."""
    path = state_dir() / SETTINGS_FILE
    if not path.exists():
        return {}
    try:
        values = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f"{path} is not valid JSON ({error})") from error
    if not isinstance(values, dict):
        raise ValueError(f"{path} must hold a JSON object of settings")
    unknown = sorted(set(values) - set(SETTING_NAMES) - set(TABLE_NAMES))
    if unknown:
        raise ValueError(f"{path} has settings the scan does not have: {', '.join(unknown)}")
    return values


def _file_settings() -> dict[str, str]:
    """The single-value settings in scan.json, as the text the environment would give."""
    return {f"REACHY_SCAN_{name.upper()}": str(value) for name, value in _read_file().items() if name in SETTING_NAMES}


def read_tables() -> tuple[dict[str, Any], dict[str, Any]]:
    """The ``models`` and ``tiers`` entries of scan.json (empty when absent), to pass to ``reachy_lib.detection``."""
    values = _read_file()
    tables = []
    for name in TABLE_NAMES:
        table = values.get(name, {})
        if not isinstance(table, dict):
            raise ValueError(f"{SETTINGS_FILE}: {name!r} must be a JSON object")
        tables.append(table)
    return tables[0], tables[1]


ENV_NAMES = {  # settings whose REACHY_SCAN_ name is not simply the field name in capitals
    "body_min_deg": "BODY_YAW_MIN_DEG",
    "body_max_deg": "BODY_YAW_MAX_DEG",
    "head_min_deg": "HEAD_YAW_MIN_DEG",
    "head_max_deg": "HEAD_YAW_MAX_DEG",
}
RULES: tuple[tuple[str, str, Callable[[float], bool]], ...] = (  # (setting, what a good value is, the test)
    ("overlap", "from 0 up to but not including 1", lambda v: 0 <= v < 1),
    ("settle_s", "not negative", lambda v: v >= 0),
    ("crop", "above 0 and at most 1", lambda v: 0 < v <= 1),
    ("confidence", "above 0 and below 1", lambda v: 0 < v < 1),
    ("nms_iou", "above 0 and below 1", lambda v: 0 < v < 1),
    ("analysis_threads", "a whole number, 1 or more", lambda v: v >= 1 and v == int(v)),
    ("stale_after_s", "above 0", lambda v: v > 0),
    ("merge_tolerance_deg", "not negative", lambda v: v >= 0),
    ("merge_overlap", "above 0 and at most 1", lambda v: 0 < v <= 1),
)


@dataclass(frozen=True)
class ScanSettings:
    """What the scan needs to know about the robot, with the agreed defaults.

    Attributes:
        overlap: Fraction of each frame shared with the next, from 0 up to but not including 1.
        hfov_deg: Camera horizontal field of view.
        body_min_deg: Body yaw limit on the right (negative; SDK sign, positive is left).
        body_max_deg: Body yaw limit on the left. The limits need not be equal.
        head_min_deg: Head yaw limit relative to the body, right (negative).
        head_max_deg: Head yaw limit relative to the body, left.
        pitch_deg: Head pitch for the whole row.
        settle_s: Seconds the robot is given to stop moving before a photo (it holds twice as long at each stop).
        crop: Central fraction of each photo's width used for analysis, above 0 up to 1 (1 is the whole photo). The
            overlap applies to this trimmed field, so a tighter crop means more stops. The field is taken as
            proportional to the width, which for a wide lens understates what is covered: the safe side.
        confidence: Detections scoring this or less are dropped (above 0, below 1).
        nms_iou: Boxes of one class overlapping more than this are merged into the strongest (above 0, below 1).
        analysis_threads: CPU threads the detector may use; 1 keeps the robot's other work responsive.
        stale_after_s: Seconds after a scan before what the robot knows is called stale (old information).
        merge_tolerance_deg: Angle allowed between two views of one object (parallax and lens error).
        merge_overlap: Share of the smaller direction box two views must share to be one object (above 0, up to 1).
    """

    overlap: float = 0.25
    hfov_deg: float = 87.0
    body_min_deg: float = -125.0  # measured cable limits with a margin, as in voice_look; recalibrate on the robot
    body_max_deg: float = 140.0
    head_min_deg: float = -35.0  # voice_look's head reach; the SDK allows 65
    head_max_deg: float = 35.0
    pitch_deg: float = 0.0
    settle_s: float = 0.5
    crop: float = 1.0
    confidence: float = 0.35
    nms_iou: float = 0.5
    analysis_threads: int = 1
    stale_after_s: float = 900.0
    merge_tolerance_deg: float = 3.0
    merge_overlap: float = 0.5

    @classmethod
    def load(cls, environ: Mapping[str, str]) -> "ScanSettings":
        """The settings for this scan: code defaults, then ``scan.json`` in the state folder, then ``environ``.

        Args:
            environ: Environment-like mapping, normally ``os.environ``; its ``REACHY_SCAN_*`` values win.

        Returns:
            The settings.

        Raises:
            ValueError: ``scan.json`` is not a JSON object, names a setting the scan does not have, or any value
                (from the file or the environment) is invalid.
        """
        return cls.from_env({**_file_settings(), **environ})

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "ScanSettings":
        """Read ``REACHY_SCAN_*`` settings from ``environ``.

        Args:
            environ: Environment-like mapping, normally ``os.environ``.

        Returns:
            The settings, with defaults for anything not set.

        Raises:
            ValueError: A value is not a number, the overlap is outside 0 <= overlap < 1, the settle time is
                negative, or a yaw range does not include zero (the plan relies on straight ahead being reachable).
        """
        defaults = cls()
        values: dict[str, Any] = {
            f.name: _number(environ, f"REACHY_SCAN_{ENV_NAMES.get(f.name, f.name.upper())}", getattr(defaults, f.name))
            for f in fields(cls)
        }
        for name, good, passes in RULES:
            if not passes(values[name]):
                raise ValueError(f"REACHY_SCAN_{ENV_NAMES.get(name, name.upper())} must be {good}, got {values[name]}")
        settings = cls(**{**values, "analysis_threads": int(values["analysis_threads"])})
        ranges = (
            ("BODY", settings.body_min_deg, settings.body_max_deg),
            ("HEAD", settings.head_min_deg, settings.head_max_deg),
        )
        for part, low, high in ranges:
            if not low <= 0 <= high:
                raise ValueError(
                    f"REACHY_SCAN_{part}_YAW_MIN_DEG and REACHY_SCAN_{part}_YAW_MAX_DEG must bracket zero, "
                    f"got {low} to {high}"
                )
        return settings
