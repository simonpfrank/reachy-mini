"""Turn daemon log lines (``journalctl -o short-iso`` text) into events.

App output reaches the daemon log wrapped by the app runner, e.g.
``... runner - WARNING - 2026-10-13 14:00:29,940 INFO <app logger>:862 | <message>``;
the app's own level (INFO above) is the one that counts, not the wrapper's WARNING.

Kept: tool calls (with arguments), tool starts (including idle-triggered ones),
cancelled tools, photos sent to the AI (camera.image), session starts, every INFO line from our own
external tools (tool.log), and any WARNING/ERROR. The app's other INFO (about 16,000 lines an hour) is dropped.

Usage:
    event = event_from_log_line(line)  # Event or None
"""

import json
import re
from datetime import datetime
from typing import Any

from reachy_hub.events import Event

JOURNAL = re.compile(r"^(?P<ts>\d{4}-\d\d-\d\dT\S+) \S+ [^:]+: (?P<rest>.*)$")
APP_RECORD = re.compile(
    r"^reachy_mini\.apps\.manager\.runner - \w+ - (?P<when>\S+ \S+) (?P<level>[A-Z]+) (?P<logger>[\w.]+):\d+ \| "
    r"(?P<msg>.*)$"
)
APP_TIME_FORMAT = "%Y-%m-%d %H:%M:%S,%f"
DAEMON_RECORD = re.compile(r"^(?P<logger>[\w.]+) - (?P<level>[A-Z]+) - (?P<msg>.*)$")
TOOL_CALL = re.compile(
    r"^Tool call received — tool_name='(?P<tool>[^']*)', call_id=(?P<call_id>[^,]+), args=(?P<args>.*)$"
)
TOOL_START = re.compile(r"^Started background tool: (?P<tool>\S+) \(id=(?P<id>[^)]+)\)$")
TOOL_CANCELLED = re.compile(r"^Cancelled tool: (?P<tool>\S+) \(id=(?P<id>[^)]+)\)$")
TOOL_OK = re.compile(r"^Tool '(?P<tool>[^']+)' \(id=(?P<id>[^)]+)\) executed successfully\.$")
TOOL_FAILED = re.compile(r"^Tool '(?P<tool>[^']+)' \(id=(?P<id>[^)]+)\) failed with error: (?P<error>.*)$")
TOOL_RESULT = re.compile(r"^role=assistant content=(?P<json>\{.*)$")  # the app cuts long lines (~700 chars)
RESULT_FIELD = re.compile(r'"(?P<key>status|namespaced_tool_name|tool)": "(?P<value>[^"]*)"')
CONTENT_START = '"text": "'
ERROR_IN_TEXT = re.compile(r"""['"]error['"]\s*:\s*(?P<q>['"])(?P<error>.*?)(?P=q)\s*[,}]""")
RESULT_PREVIEW_CHARS = 300
CAMERA_IMAGE = re.compile(r"^Added camera image to conversation jpeg_bytes=(?P<bytes>\d+)")
SESSION = re.compile(r"^Realtime session initialized with profile='(?P<profile>[^']*)' voice='(?P<voice>[^']*)'")
LEVEL_KIND = {"WARNING": "log.warning", "ERROR": "log.error", "CRITICAL": "log.error"}
TOOL_MANAGER = "background_tool_manager"
OUR_TOOLS = "reachy_mini_conversation_app._external_tools."


def _args(raw: str) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _parse_result(raw: str) -> tuple[dict[str, Any] | None, bool]:
    """Parse the logged result JSON; if the app cut the line short, recover the key fields by pattern."""
    try:
        result = json.loads(raw)
        return (result if isinstance(result, dict) else None), False
    except ValueError:
        fields: dict[str, Any] = {}
        for m in RESULT_FIELD.finditer(raw):
            fields.setdefault(m["key"], m["value"])
        return fields, True


def _tool_result(msg: str) -> dict[str, Any] | None:
    """A tool's output as logged by the app's console (``role=assistant content={...}``), or None.

    ``status: ok`` only means the call reached the tool; the tool's own text can still
    carry an error (e.g. a remote search service failing), so that error is pulled out.
    Long results are cut by the app (``truncated``); the preview then starts at the content.
    """
    match = TOOL_RESULT.match(msg)
    if match is None:
        return None
    raw = match["json"]
    result, truncated = _parse_result(raw)
    if not result or "status" not in result:
        return None
    if truncated:
        start = raw.find(CONTENT_START)
        text = raw[start + len(CONTENT_START) :] if start >= 0 else raw
    else:
        text = str(result.get("text") or json.dumps(result))
    found = ERROR_IN_TEXT.search(text)
    error = found["error"] if found else result.get("error")
    return {
        "tool": result.get("namespaced_tool_name") or result.get("tool"),
        "status": result["status"],
        "error": error,
        "truncated": truncated,
        "text": text[:RESULT_PREVIEW_CHARS],
    }


def _app_kind_and_data(logger: str, msg: str) -> tuple[str, dict[str, Any]] | None:
    """Recognise the app messages we track; None for anything else."""
    if m := TOOL_CALL.match(msg):
        return "tool.call", {"tool": m["tool"], "call_id": m["call_id"], "args": _args(m["args"])}
    if logger.endswith(TOOL_MANAGER) and (m := TOOL_START.match(msg)):
        return "tool.start", {"tool": m["tool"], "id": m["id"]}
    if m := TOOL_CANCELLED.match(msg):
        return "tool.cancelled", {"tool": m["tool"], "id": m["id"]}
    if m := TOOL_OK.match(msg):
        return "tool.done", {"tool": m["tool"], "id": m["id"]}
    if m := TOOL_FAILED.match(msg):
        return "tool.failed", {"tool": m["tool"], "id": m["id"], "error": m["error"]}
    if logger.endswith(".console") and (result := _tool_result(msg)):
        return "tool.result", result
    if m := CAMERA_IMAGE.match(msg):
        size = int(m["bytes"])
        return "camera.image", {"bytes": size, "kb": round(size / 1024)}
    if m := SESSION.match(msg):
        return "app.session", {"profile": m["profile"], "voice": m["voice"]}
    if logger.startswith(OUR_TOOLS):
        return "tool.log", {"tool": logger.removeprefix(OUR_TOOLS), "message": msg}
    return None


def event_from_log_line(line: str) -> Event | None:
    """Parse one daemon log line.

    Args:
        line: One line from the daemon's ``/api/logs/ws/daemon`` stream.

    Returns:
        An Event timed from the log line, or None for lines we do not track.
    """
    journal = JOURNAL.match(line)
    if journal is None:
        return None
    time = datetime.fromisoformat(journal["ts"])
    record = APP_RECORD.match(journal["rest"])
    source = "app"
    if record is not None:  # the app's own timestamp has milliseconds; the journal's has whole seconds
        time = datetime.strptime(record["when"], APP_TIME_FORMAT).replace(tzinfo=time.tzinfo)
    else:
        record, source = DAEMON_RECORD.match(journal["rest"]), "daemon"
    if record is None:
        return None
    tracked = _app_kind_and_data(record["logger"], record["msg"]) if source == "app" else None
    if tracked:
        return Event(time, source, tracked[0], tracked[1])
    kind = LEVEL_KIND.get(record["level"])
    if kind is None:
        return None
    return Event(time, source, kind, {"logger": record["logger"], "message": record["msg"]})
