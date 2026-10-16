import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

from reachy_hub.store import Store

NOW = datetime(2026, 10, 13, 16, 0, 0, tzinfo=UTC)


def _note(method: str, **params: object) -> dict[str, object]:
    return {"jsonrpc": "2.0", "method": method, "params": params}


def test_level_updates_live_values_not_event_list() -> None:
    store = Store()
    store.add_rpc(_note("conversation.level", role="user", rms=0.2), NOW)
    store.add_rpc(_note("conversation.level", role="assistant", rms=0.5), NOW)
    assert (store.user_level, store.robot_level) == (0.2, 0.5)
    assert store.events == []


def test_other_app_events_go_to_event_list() -> None:
    store = Store()
    store.add_rpc(_note("conversation.turn", state="speaking"), NOW)
    assert [e.kind for e in store.events] == ["conversation.turn"]


def test_rpc_reply_is_ignored() -> None:
    store = Store()
    store.add_rpc({"jsonrpc": "2.0", "id": 1, "result": {}}, NOW)
    assert store.events == []


def test_robot_state_is_replaced_by_latest() -> None:
    store = Store()
    store.set_robot({"control_mode": "disabled", "timestamp": "a"})
    store.set_robot({"control_mode": "enabled", "timestamp": "b"})
    assert store.robot is not None and store.robot.motor_mode == "enabled"


def test_link_change_is_logged_once() -> None:
    store = Store()
    store.set_link("app", "connected", NOW)
    store.set_link("app", "connected", NOW)
    store.set_link("app", "disconnected: closed", NOW)
    assert store.app_link == "disconnected: closed"
    assert [e.data["status"] for e in store.events] == ["connected", "disconnected: closed"]


def test_event_list_is_capped() -> None:
    store = Store(max_events=3)
    for i in range(5):
        store.add_rpc(_note("conversation.activity", n=i), NOW)
    assert [e.data["n"] for e in store.events] == [2, 3, 4]


def _imu(z: float) -> dict[str, object]:
    return {"imu": {"accelerometer": [0.0, 0.0, z], "gyroscope": [0.0, 0.0, 0.0]}}


def test_imu_tap_becomes_robot_event() -> None:
    store = Store()
    for i in range(20):
        store.add_imu(_imu(9.75), datetime.fromtimestamp(1000 + i / 45, UTC))
    store.add_imu(_imu(15.0), datetime.fromtimestamp(1001, UTC))
    assert [(e.source, e.kind) for e in store.events] == [("robot", "imu.tap")]
    assert store.events[0].data["strength"] > 2.0


def test_latest_imu_reading_is_kept_live() -> None:
    store = Store()
    store.add_imu(_imu(9.75), NOW)
    store.add_imu(_imu(9.80), NOW)
    snap = store.snapshot()["imu"]
    assert snap["latest"]["accel"] == 9.8 and snap["latest"]["tilt_deg"] == 0.0


def test_last_tap_is_kept_for_the_panel() -> None:
    store = Store()
    assert store.snapshot()["imu"]["last_tap"] is None
    for i in range(20):
        store.add_imu(_imu(9.75), datetime.fromtimestamp(1000 + i / 45, UTC))
    store.add_imu(_imu(15.0), datetime.fromtimestamp(1001, UTC))
    last_tap = store.snapshot()["imu"]["last_tap"]
    assert last_tap["strength"] > 2.0 and "direction_deg" in last_tap
    assert last_tap["time"] == datetime.fromtimestamp(1001, UTC).isoformat()


def test_imu_message_without_imu_is_ignored() -> None:
    store = Store()
    store.add_imu({"control_mode": "enabled"}, NOW)
    store.add_imu("junk", NOW)
    assert store.events == []


LOG_LINES = (Path(__file__).parent.parent / "data" / "daemon_log_sample.txt").read_text().splitlines()
MORNING = datetime(2026, 10, 13, 0, 0, tzinfo=UTC)


def test_log_lines_older_than_the_store_are_ignored() -> None:
    store = Store()  # started now: the sample lines are from earlier today
    for line in LOG_LINES:
        store.add_log_line(line)
    assert store.events == []


def test_log_events_are_kept_and_duplicates_skipped() -> None:
    store = Store(since=MORNING)
    store.add_log_line(LOG_LINES[1])
    store.add_log_line(LOG_LINES[1])
    assert [e.kind for e in store.events] == ["tool.call"]


def test_tool_done_gets_duration_from_its_call() -> None:
    store = Store(since=MORNING)
    store.add_log_line(LOG_LINES[11])  # search requested at 17:50:55.176
    store.add_log_line(LOG_LINES[12])  # executed successfully at 17:51:04.409
    done = store.events[-1]
    assert done.kind == "tool.done"
    assert done.data["seconds"] == 9.23


def test_tool_done_without_a_known_call_has_no_duration() -> None:
    store = Store(since=MORNING)
    store.add_log_line(LOG_LINES[12])
    assert "seconds" not in store.events[-1].data


def test_snapshot_is_json_ready() -> None:
    store = Store()
    store.set_robot({"control_mode": "enabled", "timestamp": "t"})
    store.add_rpc(_note("conversation.turn", state="listening"), NOW)
    snap = json.loads(json.dumps(store.snapshot()))
    assert snap["robot"]["motor_mode"] == "enabled"
    assert snap["events"][0] == {
        "seq": 1, "time": NOW.isoformat(), "source": "app", "kind": "conversation.turn", "data": {"state": "listening"}
    }
    assert set(snap) == {
        "robot", "user_level", "robot_level", "app_link", "robot_link", "imu_link", "log_link", "imu", "sound",
        "events",
    }


def _activity(reason: str) -> dict[str, object]:
    return _note("conversation.activity", reason=reason)


def test_streaming_deltas_become_started_and_ended() -> None:
    store = Store()
    for i in range(3):
        store.add_rpc(_activity("assistant_audio_delta"), datetime.fromtimestamp(1000 + i * 0.5, UTC))
    store.add_rpc(_activity("assistant_transcript_done"), datetime.fromtimestamp(1002, UTC))
    kinds = [(e.kind, e.data.get("stream") or e.data.get("reason")) for e in store.events]
    assert kinds == [
        ("stream.started", "assistant_audio_delta"),
        ("stream.ended", "assistant_audio_delta"),
        ("conversation.activity", "assistant_transcript_done"),
    ]
    assert store.events[1].data == {"stream": "assistant_audio_delta", "chunks": 3, "seconds": 1.0}


def test_partial_transcripts_collapse_but_final_is_kept() -> None:
    store = Store()
    for text in ("He", "Hello", "Hello rob"):
        store.add_rpc(_note("conversation.transcript", role="user", text=text, final=False), NOW)
    store.add_rpc(_note("conversation.transcript", role="user", text="Hello robot", final=True), NOW)
    kinds = [e.kind for e in store.events]
    assert kinds == ["stream.started", "stream.ended", "conversation.transcript"]
    assert store.events[1].data["last_text"] == "Hello rob"
    assert store.events[-1].data["text"] == "Hello robot"


def test_a_different_stream_ends_the_previous_one() -> None:
    store = Store()
    store.add_rpc(_activity("user_transcription_delta"), NOW)
    store.add_rpc(_activity("assistant_audio_delta"), NOW)
    assert [e.kind for e in store.events] == ["stream.started", "stream.ended", "stream.started"]


def test_user_speech_gives_heard_summary_with_duration_and_peak_level() -> None:
    store = Store()
    store.add_rpc(_activity("user_speech_started"), datetime.fromtimestamp(1000, UTC))
    for rms in (0.1, 0.6, 0.3):
        store.add_rpc(_note("conversation.level", role="user", rms=rms), datetime.fromtimestamp(1001, UTC))
    store.add_rpc(_note("conversation.level", role="assistant", rms=0.9), datetime.fromtimestamp(1001, UTC))
    store.add_rpc(_activity("user_speech_stopped"), datetime.fromtimestamp(1002.5, UTC))
    heard = store.events[-1]
    assert (heard.kind, heard.data) == ("speech.heard", {"seconds": 2.5, "peak_level": 0.6})


def test_speech_stopped_without_start_gives_no_summary() -> None:
    store = Store()
    store.add_rpc(_activity("user_speech_stopped"), NOW)
    assert [e.kind for e in store.events] == ["conversation.activity"]


def test_clear_events_empties_the_list_but_keeps_state_and_numbering() -> None:
    store = Store()
    store.set_robot({"control_mode": "enabled", "timestamp": "t"})
    store.add_rpc(_note("conversation.turn", state="speaking"), NOW)
    assert store.clear_events() == 1
    assert store.events == []
    assert store.robot is not None
    store.add_rpc(_note("conversation.turn", state="listening"), NOW)
    assert store.snapshot()["events"][0]["seq"] == 2


def _doa_state(angle_rad: float, speech: bool) -> dict[str, object]:
    return {"control_mode": "enabled", "timestamp": "t", "doa": {"angle": angle_rad, "speech_detected": speech}}


def test_sound_flag_share_covers_the_last_two_seconds() -> None:
    store = Store()
    for tenth in range(40):  # 4 s at 10 Hz; flag on only in the last second
        when = NOW + timedelta(seconds=tenth / 10)
        store.set_robot(_doa_state(1.57, tenth >= 30), when)
    assert store.snapshot()["sound"]["flag_pct"] == 50


def test_sound_direction_is_the_last_flagged_reading_not_the_frozen_value() -> None:
    store = Store()
    store.set_robot(_doa_state(math.pi / 2 + 0.5, True), NOW)
    store.set_robot(_doa_state(math.pi / 2, False), NOW + timedelta(seconds=3))
    sound = store.snapshot()["sound"]
    assert sound["fresh_dir_deg"] == -28.6
    assert sound["fresh_time"] == NOW.isoformat()


def test_sound_summary_is_empty_before_any_reading() -> None:
    assert Store().snapshot()["sound"] == {"flag_pct": None, "fresh_dir_deg": None, "fresh_time": None}


def test_levels_are_cleared_when_the_app_disconnects() -> None:
    store = Store()
    store.add_rpc(_note("conversation.level", role="user", rms=0.3), NOW)
    store.set_link("app", "connected", NOW)
    store.set_link("app", "disconnected: closed", NOW)
    assert (store.user_level, store.robot_level) == (None, None)
