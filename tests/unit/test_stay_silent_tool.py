"""Tests for the on-device ``stay_silent`` tool. Stand-in for the app's Tool base, which only exists on the robot."""

import asyncio
import sys
import types
from typing import Any


class _StandInTool:
    name: str
    description: str
    parameters_schema: dict[str, Any]
    needs_response: bool = True


_core_tools = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
_core_tools.Tool = _StandInTool  # type: ignore[attr-defined]
_core_tools.ToolDependencies = object  # type: ignore[attr-defined]
for name in ("reachy_mini_conversation_app", "reachy_mini_conversation_app.tools"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules.setdefault("reachy_mini_conversation_app.tools.core_tools", _core_tools)

from robot_tools import stay_silent  # noqa: E402


def test_tool_ends_the_turn_without_a_spoken_reply() -> None:
    tool = stay_silent.StaySilent()
    assert tool.name == "stay_silent"
    assert tool.needs_response is False


def test_tool_reports_why_it_stayed_silent() -> None:
    result = asyncio.run(stay_silent.StaySilent()(object(), reason="television"))
    assert result == {"status": "silent", "reason": "television"}


def test_reason_defaults_when_missing() -> None:
    result = asyncio.run(stay_silent.StaySilent()(object()))
    assert result == {"status": "silent", "reason": "not addressed"}
