"""sleep tool: start the wake watcher, then run Pollen's sleep; stay awake if the watcher cannot start.
The conversation app's Tool base only exists on the robot, so a stand-in module is registered before import."""

import asyncio
import subprocess
import sys
import types
from typing import Any

import pytest

_core_tools = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
_core_tools.Tool = object  # type: ignore[attr-defined]
_core_tools.ToolDependencies = object  # type: ignore[attr-defined]
for name in ("reachy_mini_conversation_app", "reachy_mini_conversation_app.tools"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules.setdefault("reachy_mini_conversation_app.tools.core_tools", _core_tools)

from robot_tools import sleep  # noqa: E402


@pytest.fixture
def systemd(monkeypatch):
    """Record systemctl/systemd-run calls; ``active`` sets what is-active reports."""
    calls: list[tuple[list[str], dict[str, Any]]] = []
    state = types.SimpleNamespace(active="inactive", fail=False, calls=calls)

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[0].endswith("systemctl"):
            return subprocess.CompletedProcess(args, 0, stdout=state.active + "\n")
        if state.fail:
            raise subprocess.CalledProcessError(1, args, stderr="Failed to start")
        return subprocess.CompletedProcess(args, 0, stdout="")

    monkeypatch.setattr(sleep.subprocess, "run", run)
    return state


def test_watcher_starts_as_a_user_unit_in_the_project(systemd):
    sleep.start_watcher()
    args, kwargs = systemd.calls[-1]
    assert args[0].endswith("systemd-run") and args[1:4] == ["--user", f"--unit={sleep.UNIT}", "--collect"]
    assert f"--working-directory={sleep.ROOT}" in args
    assert args[-3:] == [str(sleep.WAKE_PYTHON), "-m", "reachy_wake"]
    assert kwargs["env"]["XDG_RUNTIME_DIR"].startswith("/run/user/") and "shell" not in kwargs


def test_a_running_watcher_is_not_started_twice(systemd):
    systemd.active = "active"
    sleep.start_watcher()
    assert [args[0].rsplit("/", 1)[-1] for args, _ in systemd.calls] == ["systemctl"]


def call_tool(deps: Any) -> dict[str, Any]:
    return asyncio.run(sleep.Sleep()(deps))


def test_sleep_starts_the_watcher_then_runs_pollens_sleep(systemd):
    slept: list[bool] = []
    deps = types.SimpleNamespace(go_to_sleep=lambda: slept.append(True) or {"status": "sleeping"})
    assert call_tool(deps) == {"status": "sleeping"}
    assert slept == [True] and systemd.calls[-1][0][0].endswith("systemd-run")


def test_stays_awake_if_the_watcher_cannot_start(systemd):
    systemd.fail = True
    deps = types.SimpleNamespace(go_to_sleep=lambda: pytest.fail("must not sleep without a watcher"))
    assert "stayed awake" in call_tool(deps)["error"]


def test_unavailable_without_pollens_sleep(systemd):
    assert "unavailable" in call_tool(types.SimpleNamespace(go_to_sleep=None))["error"]
    assert systemd.calls == []
