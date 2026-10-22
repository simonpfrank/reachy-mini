"""room_scan planning: the fixed pose sequence that covers the robot's full reach."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "robot_tools" / "room_scan.py"


@pytest.fixture
def scan(monkeypatch):
    core = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
    core.Tool = type("Tool", (), {})
    core.ToolDependencies = types.SimpleNamespace
    monkeypatch.setitem(sys.modules, core.__name__, core)
    spec = importlib.util.spec_from_file_location("_room_scan_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def planned(scan, **env):
    return scan.plan(scan.ScanSettings.from_env({k: str(v) for k, v in env.items()}))


def test_settings_default_to_the_agreed_values(scan):
    s = scan.ScanSettings.from_env({})
    assert (s.overlap, s.hfov_deg, s.pitch_deg, s.settle_s) == (0.25, 87.0, 0.0, 0.5)
    assert (s.body_min_deg, s.body_max_deg, s.head_min_deg, s.head_max_deg) == (-125, 140, -35, 35)


def test_settings_come_from_the_environment(scan):
    s = scan.ScanSettings.from_env(
        {"REACHY_SCAN_OVERLAP": "0.4", "REACHY_SCAN_BODY_YAW_MIN_DEG": "-120", "REACHY_SCAN_HEAD_YAW_MAX_DEG": "70"}
    )
    assert s.overlap == 0.4 and s.body_min_deg == -120 and s.head_max_deg == 70


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("REACHY_SCAN_BODY_YAW_MIN_DEG", "10"),  # zero must lie inside the range
        ("REACHY_SCAN_BODY_YAW_MAX_DEG", "-10"),
        ("REACHY_SCAN_HEAD_YAW_MIN_DEG", "5"),
        ("REACHY_SCAN_HEAD_YAW_MAX_DEG", "-5"),
    ],
)
def test_a_range_that_excludes_zero_is_refused(scan, name, value):
    with pytest.raises(ValueError, match=name):
        scan.ScanSettings.from_env({name: value})


def test_the_settle_time_comes_from_the_environment_and_cannot_be_negative(scan):
    assert scan.ScanSettings.from_env({"REACHY_SCAN_SETTLE_S": "0.8"}).settle_s == 0.8
    with pytest.raises(ValueError, match="REACHY_SCAN_SETTLE_S"):
        scan.ScanSettings.from_env({"REACHY_SCAN_SETTLE_S": "-1"})


@pytest.mark.parametrize("value", ["-0.1", "1", "1.5", "abc"])
def test_a_bad_overlap_is_refused(scan, value):
    with pytest.raises(ValueError, match="REACHY_SCAN_OVERLAP"):
        scan.ScanSettings.from_env({"REACHY_SCAN_OVERLAP": value})


def test_default_plan_runs_from_full_reach_one_side_to_the_other(scan):
    poses = planned(scan)
    assert len(poses) == 7
    assert (poses[0].body_yaw_deg, poses[0].head_yaw_deg) == (-125, -35)
    assert (poses[-1].body_yaw_deg, poses[-1].head_yaw_deg) == (140, 35)


def test_camera_headings_are_evenly_spaced_within_the_overlap_limit(scan):
    headings = [p.body_yaw_deg + p.head_yaw_deg for p in planned(scan)]
    steps = [b - a for a, b in zip(headings, headings[1:], strict=False)]
    assert max(steps) - min(steps) < 1e-9
    assert max(steps) <= 87.0 * 0.75 + 1e-9


def test_no_pose_goes_past_the_body_or_head_limit(scan):
    for pose in planned(scan):
        assert -125 - 1e-9 <= pose.body_yaw_deg <= 140 + 1e-9 and abs(pose.head_yaw_deg) <= 35 + 1e-9


def test_the_head_turns_only_beyond_the_bodys_reach(scan):
    for pose in planned(scan):
        if -125 <= pose.body_yaw_deg + pose.head_yaw_deg <= 140:
            assert pose.head_yaw_deg == 0


def test_unequal_left_and_right_limits_are_each_respected(scan):
    poses = planned(
        scan,
        REACHY_SCAN_BODY_YAW_MIN_DEG=-100,
        REACHY_SCAN_BODY_YAW_MAX_DEG=150,
        REACHY_SCAN_HEAD_YAW_MIN_DEG=-60,
        REACHY_SCAN_HEAD_YAW_MAX_DEG=70,
    )
    assert len(poses) == 7  # headings -160 to +220 is 380 degrees
    assert (poses[0].body_yaw_deg, poses[0].head_yaw_deg) == (-100, -60)
    assert (poses[-1].body_yaw_deg, poses[-1].head_yaw_deg) == (150, 70)
    for pose in poses:
        assert -100 - 1e-9 <= pose.body_yaw_deg <= 150 + 1e-9
        assert -60 - 1e-9 <= pose.head_yaw_deg <= 70 + 1e-9


def test_less_overlap_needs_fewer_frames(scan):
    assert len(planned(scan, REACHY_SCAN_OVERLAP=0)) == 5


def test_every_pose_holds_the_configured_pitch(scan):
    assert {p.pitch_deg for p in planned(scan, REACHY_SCAN_PITCH_DEG=-5)} == {-5.0}


def test_without_a_crop_the_whole_photo_is_used(scan):
    assert scan.ScanSettings().crop == 1.0 and len(planned(scan)) == 7


@pytest.mark.parametrize(("crop", "stops"), [(0.8, 8), (0.7, 9), (0.6, 10)])
def test_a_tighter_crop_needs_more_stops_to_cover_the_same_sweep(scan, crop, stops):
    poses = planned(scan, REACHY_SCAN_CROP=crop)
    assert len(poses) == stops
    assert (poses[0].body_yaw_deg, poses[0].head_yaw_deg) == (-125, -35)  # the sweep still runs limit to limit
    assert (poses[-1].body_yaw_deg, poses[-1].head_yaw_deg) == (140, 35)


def test_the_overlap_applies_to_the_trimmed_field_of_view(scan):
    poses = planned(scan, REACHY_SCAN_CROP=0.7)
    headings = [p.body_yaw_deg + p.head_yaw_deg for p in poses]
    steps = [b - a for a, b in zip(headings, headings[1:], strict=False)]
    assert max(steps) <= 87.0 * 0.7 * 0.75 + 1e-9


@pytest.mark.parametrize("value", ["0", "-0.5", "1.01", "abc"])
def test_a_bad_crop_is_refused_by_name(scan, value):
    with pytest.raises(ValueError, match="REACHY_SCAN_CROP"):
        scan.ScanSettings.from_env({"REACHY_SCAN_CROP": value})


def test_crop_is_a_setting_scan_json_may_hold(scan):
    from reachy_lib.scan_settings import SETTING_NAMES  # importable: loading the scan tool put its folder on the path

    assert "crop" in SETTING_NAMES
