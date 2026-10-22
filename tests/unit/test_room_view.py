"""room_view: what the robot knows about the room, in plain anonymous words; read-only; honest about age and gaps."""

import asyncio
import importlib.util
import json
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "robot_tools"
TOOL = TOOLS / "room_view.py"


@pytest.fixture
def view(monkeypatch, tmp_path):
    core = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
    core.Tool = type("Tool", (), {})
    core.ToolDependencies = types.SimpleNamespace
    monkeypatch.setitem(sys.modules, core.__name__, core)
    monkeypatch.setenv("REACHY_TOOLS_SCAN_DIR", str(tmp_path / "scan"))
    monkeypatch.setenv("REACHY_TOOLS_STATE_DIR", str(tmp_path / "state"))
    spec = importlib.util.spec_from_file_location("_room_view_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from reachy_lib import world

    def save(minutes_ago=1, status="complete", objects=None, stale=None):
        updated = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
        world.write_world(
            {
                "scan_started": updated,
                "updated": updated,
                "status": status,
                "coverage": {"photos_taken": 7, "photos_total": 7, "analysed": {"now": 7}},
                "objects": objects if objects is not None else [BOTTLE],
                "stale_objects": stale or [],
            }
        )

    def call():
        return asyncio.run(module.RoomView()(types.SimpleNamespace()))

    return types.SimpleNamespace(module=module, save=save, call=call, tmp=tmp_path, monkeypatch=monkeypatch)


BOTTLE = {
    "label": "bottle", "bearing_deg": 12.0, "left_deg": 15.0, "right_deg": 9.0, "vertical_deg": 0.0,
    "best_score": 0.82, "tiers": ["now", "after"], "photos": [2, 3], "confirmed": True,
}  # fmt: skip


def test_with_no_scan_it_says_it_has_not_looked(view):
    reply = view.call()
    assert reply["state"] == "no_scan" and reply["objects"] == [] and "not scanned" in reply["note"]


def test_a_recent_scan_is_described_in_plain_words(view):
    view.save()
    reply = view.call()
    assert reply["state"] == "fresh" and reply["coverage"] == "7 of 7 directions"
    assert reply["objects"] == [{"what": "bottle", "where": "straight ahead", "bearing_deg": 10, "how_sure": "sure"}]
    assert reply["counts"] == {"bottle": 1}


def test_an_old_scan_is_called_old_and_a_rescan_is_offered(view):
    view.save(minutes_ago=240)
    reply = view.call()
    assert reply["state"] == "stale" and "old" in reply["note"] and "scan" in reply["note"]


def test_how_old_is_old_comes_from_the_scan_settings(view):
    view.save(minutes_ago=2)
    assert view.call()["state"] == "fresh"
    view.monkeypatch.setenv("REACHY_SCAN_STALE_AFTER_S", "60")
    assert view.call()["state"] == "stale"


def test_a_mistake_in_the_settings_file_does_not_stop_the_answer(view):
    view.save()
    (view.tmp / "state").mkdir()
    (view.tmp / "state" / "scan.json").write_text(json.dumps({"overlp": 1}))
    reply = view.call()
    assert reply["state"] == "fresh" and "mistake" in reply["note"]


def test_a_damaged_picture_is_reported_not_hidden(view):
    (view.tmp / "scan").mkdir()
    (view.tmp / "scan" / "world.json").write_text("{broken")
    reply = view.call()
    assert reply["state"] == "unavailable" and "damaged" in reply["note"] and reply["objects"] == []


def test_a_scan_in_progress_says_so_and_keeps_the_old_picture_apart(view):
    view.save(status="scanning", objects=[], stale=[{**BOTTLE, "stale": True, "as_of": "2026-10-20T10:00:00+00:00"}])
    reply = view.call()
    assert reply["state"] == "scanning" and reply["objects"] == [] and reply["older"][0]["what"] == "bottle"


def test_the_reply_is_plain_data_and_names_nobody(view):
    view.save()
    reply = view.call()
    text = json.dumps(reply)
    assert str(view.tmp) not in text  # no folder path in the reply
    assert set(reply) >= {"state", "objects", "note"}


def test_the_tool_tells_the_model_what_it_is_for(view):
    tool = view.module.RoomView
    assert tool.name == "room_view" and tool.parameters_schema["required"] == []
    assert "room_scan" in tool.description and "cannot see" in tool.description
