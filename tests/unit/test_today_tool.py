"""Tests for the on-device ``today`` tool. The conversation app's Tool base only exists on the robot, so a stand-in
module is registered before import (unit-test mock of that dependency)."""

import asyncio
import sys
import types
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest


class _StandInTool:
    name: str
    description: str
    parameters_schema: dict[str, Any]


_core_tools = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
_core_tools.Tool = _StandInTool  # type: ignore[attr-defined]
_core_tools.ToolDependencies = object  # type: ignore[attr-defined]
for name in ("reachy_mini_conversation_app", "reachy_mini_conversation_app.tools"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["reachy_mini_conversation_app.tools.core_tools"] = _core_tools

from robot_tools import today  # noqa: E402

LONDON = ZoneInfo("Europe/London")


@pytest.mark.parametrize(
    ("hour", "minute", "spoken"),
    [
        (19, 20, "twenty past seven in the evening"),
        (7, 0, "seven o'clock in the morning"),
        (12, 0, "midday"),
        (0, 0, "midnight"),
        (15, 45, "quarter to four in the afternoon"),
        (9, 7, "seven minutes past nine in the morning"),
        (22, 35, "twenty-five to eleven at night"),
        (11, 30, "half past eleven in the morning"),
        (23, 50, "ten to midnight"),
        (11, 58, "two minutes to midday"),
    ],
)
def test_spoken_time(hour: int, minute: int, spoken: str) -> None:
    assert today.spoken_time(datetime(2026, 10, 13, hour, minute, tzinfo=LONDON)) == spoken


@pytest.mark.parametrize(
    ("day", "spoken"),
    [
        (13, "Tuesday the thirteenth of October, twenty twenty-six"),
        (1, "Thursday the first of October, twenty twenty-six"),
        (22, "Thursday the twenty-second of October, twenty twenty-six"),
        (31, "Saturday the thirty-first of October, twenty twenty-six"),
    ],
)
def test_spoken_date(day: int, spoken: str) -> None:
    assert today.spoken_date(datetime(2026, 10, day, 9, 0, tzinfo=LONDON)) == spoken


def test_today_payload_has_spoken_and_plain_values() -> None:
    payload = today.today_payload(datetime(2026, 10, 13, 19, 20, tzinfo=LONDON))
    assert payload == {
        "spoken": "It's twenty past seven in the evening on Tuesday the thirteenth of October, twenty twenty-six.",
        "date": "2026-10-13",
        "weekday": "Tuesday",
        "time_24h": "19:20",
        "timezone": "BST",
    }


def test_tool_is_named_today_and_returns_payload() -> None:
    tool = today.Today()
    assert tool.name == "today"
    result = asyncio.run(tool(object()))
    assert set(result) == {"spoken", "date", "weekday", "time_24h", "timezone"}
