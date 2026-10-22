"""Scan settings: code defaults, then scan.json in the state folder (read fresh every scan), then the environment."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "robot_tools" / "room_scan.py"


@pytest.fixture
def scan(monkeypatch, tmp_path):
    core = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
    core.Tool = type("Tool", (), {})
    core.ToolDependencies = types.SimpleNamespace
    monkeypatch.setitem(sys.modules, core.__name__, core)
    monkeypatch.setenv("REACHY_TOOLS_STATE_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location("_scan_config_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return types.SimpleNamespace(module=module, file=tmp_path / "scan.json")


def test_without_a_file_the_defaults_apply(scan):
    assert scan.module.ScanSettings.load({}) == scan.module.ScanSettings()


def test_the_file_overrides_the_defaults(scan):
    scan.file.write_text(json.dumps({"overlap": 0.4, "body_yaw_min_deg": -100, "settle_s": 0.9}))
    s = scan.module.ScanSettings.load({})
    assert (s.overlap, s.body_min_deg, s.settle_s) == (0.4, -100, 0.9)
    assert s.hfov_deg == 87.0  # anything the file does not mention keeps its default


def test_an_environment_variable_overrides_the_file(scan):
    scan.file.write_text(json.dumps({"overlap": 0.4, "settle_s": 0.9}))
    s = scan.module.ScanSettings.load({"REACHY_SCAN_OVERLAP": "0.1"})
    assert s.overlap == 0.1 and s.settle_s == 0.9


def test_the_file_is_read_fresh_on_every_call(scan):
    scan.file.write_text(json.dumps({"overlap": 0.4}))
    assert scan.module.ScanSettings.load({}).overlap == 0.4
    scan.file.write_text(json.dumps({"overlap": 0.3}))
    assert scan.module.ScanSettings.load({}).overlap == 0.3
    scan.file.unlink()
    assert scan.module.ScanSettings.load({}).overlap == 0.25


def test_a_setting_the_scan_does_not_have_is_refused_by_name(scan):
    scan.file.write_text(json.dumps({"overlp": 0.4}))
    with pytest.raises(ValueError, match="overlp"):
        scan.module.ScanSettings.load({})


def test_a_file_that_is_not_valid_json_is_refused_and_named(scan):
    scan.file.write_text("{not json")
    with pytest.raises(ValueError, match="scan.json"):
        scan.module.ScanSettings.load({})


def test_a_file_that_is_not_a_dictionary_is_refused(scan):
    scan.file.write_text(json.dumps([1, 2]))
    with pytest.raises(ValueError, match="scan.json"):
        scan.module.ScanSettings.load({})


def test_values_from_the_file_are_validated_like_any_other(scan):
    scan.file.write_text(json.dumps({"overlap": 1.5}))
    with pytest.raises(ValueError, match="REACHY_SCAN_OVERLAP"):
        scan.module.ScanSettings.load({})


def test_the_model_tables_may_sit_in_the_same_file(scan):
    tables = {"models": {"yolox_nano": {"size": 480}}, "tiers": {"remote": None}}
    scan.file.write_text(json.dumps({"overlap": 0.4, **tables}))
    assert scan.module.ScanSettings.load({}).overlap == 0.4
    assert scan.module.read_tables() == ({"yolox_nano": {"size": 480}}, {"remote": None})


def test_without_a_file_there_are_no_table_overrides(scan):
    assert scan.module.read_tables() == ({}, {})


def test_a_table_that_is_not_an_object_is_refused_by_name(scan):
    scan.file.write_text(json.dumps({"models": [1, 2]}))
    with pytest.raises(ValueError, match="models"):
        scan.module.read_tables()
