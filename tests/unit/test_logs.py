from datetime import datetime
from pathlib import Path

from reachy_hub.logs import event_from_log_line

LINES = (Path(__file__).parent.parent / "data" / "daemon_log_sample.txt").read_text().splitlines()


def test_tool_call_gives_tool_name_and_parsed_args() -> None:
    event = event_from_log_line(LINES[1])
    assert event is not None
    assert (event.source, event.kind) == ("app", "tool.call")
    assert event.data["tool"] == "dance"
    assert event.data["args"] == {"move": "groovy_sway_and_roll"}
    assert event.time == datetime.fromisoformat("2026-10-13T14:00:29.940+01:00")  # app's own ms timestamp


def test_background_tool_start_is_reported_once() -> None:
    event = event_from_log_line(LINES[3])
    assert event is not None and (event.kind, event.data["tool"]) == ("tool.start", "dance")
    assert event_from_log_line(LINES[4]) is None  # same start, logged again by another module


def test_daemon_error_line() -> None:
    event = event_from_log_line(LINES[5])
    assert event is not None and (event.source, event.kind) == ("daemon", "log.error")
    assert event.data["logger"] == "reachy_mini.utils.wireless_version.startup_check"
    assert event.data["message"].startswith("Failed to update bluetooth service")


def test_app_error_uses_the_apps_own_level_not_the_wrapper() -> None:
    event = event_from_log_line(LINES[7])
    assert event is not None and (event.source, event.kind) == ("app", "log.error")
    assert event.data["message"].startswith("Realtime error [invalid_conversation_item]")


def test_session_start_gives_profile_and_voice() -> None:
    event = event_from_log_line(LINES[8])
    assert event is not None and event.kind == "app.session"
    assert event.data == {"profile": "bored_teenager", "voice": "Eric"}


def test_routine_lines_are_ignored() -> None:
    assert event_from_log_line(LINES[9]) is None  # relay INFO
    assert event_from_log_line(LINES[10]) is None  # uvicorn access
    assert event_from_log_line("not a journal line") is None


def test_cancelled_tool() -> None:
    line = (
        "2026-10-13T15:00:00+01:00 reachy-mini launcher.sh[914]: reachy_mini.apps.manager.runner - WARNING - "
        "2026-10-13 15:00:00,001 INFO reachy_mini_conversation_app.tools.background_tool_manager:250 | "
        "Cancelled tool: dance (id=call_1)"
    )
    event = event_from_log_line(line)
    assert event is not None and (event.kind, event.data) == ("tool.cancelled", {"tool": "dance", "id": "call_1"})


SEARCH = "pollen_robotics_reachy_mini_search_tool__search_web"


def test_tool_success_gives_tool_done_with_name_and_id() -> None:
    event = event_from_log_line(LINES[12])
    assert event is not None and event.kind == "tool.done"
    assert event.data == {"tool": SEARCH, "id": "call_e48b0c1edf1f43c690ed8f29c62faf84"}


def test_tool_result_shows_the_remote_error_hidden_behind_status_ok() -> None:
    event = event_from_log_line(LINES[13])
    assert event is not None and event.kind == "tool.result"
    assert event.data["tool"] == SEARCH
    assert event.data["status"] == "ok"
    assert event.data["error"] == "web search failed for 'latest movies in theaters now'"
    assert len(event.data["text"]) <= 300


def test_tool_failure_line() -> None:
    line = (
        "2026-10-13T18:00:00+01:00 reachy-mini launcher.sh[914]: reachy_mini.apps.manager.runner - WARNING - "
        "2026-10-13 18:00:00,123 ERROR reachy_mini_conversation_app.huggingface_realtime:585 | "
        "Tool 'dance' (id=call_9) failed with error: unknown move"
    )
    event = event_from_log_line(line)
    assert event is not None and (event.kind, event.data) == (
        "tool.failed", {"tool": "dance", "id": "call_9", "error": "unknown move"}
    )


def test_plain_chat_line_is_not_a_tool_result() -> None:
    line = (
        "2026-10-13T18:00:00+01:00 reachy-mini launcher.sh[914]: reachy_mini.apps.manager.runner - WARNING - "
        "2026-10-13 18:00:00,123 INFO reachy_mini_conversation_app.console:899 | role=user content=Hello robot"
    )
    assert event_from_log_line(line) is None


def test_truncated_tool_result_is_still_shown() -> None:
    event = event_from_log_line(LINES[14])  # successful search; the app cut its log line at ~700 chars
    assert event is not None and event.kind == "tool.result"
    assert (event.data["tool"], event.data["status"], event.data["error"]) == (SEARCH, "ok", None)
    assert event.data["truncated"] is True
    assert "BBC" in event.data["text"] or "url" in event.data["text"]


def test_camera_image_sent_gives_event_with_size() -> None:
    event = event_from_log_line(LINES[15])
    assert event is not None and (event.source, event.kind) == ("app", "camera.image")
    assert event.data == {"bytes": 448452, "kb": 438}
