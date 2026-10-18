"""On-device tool: go to sleep so that the wake word can wake the robot again.

Starts the wake watcher (``reachy_wake``) as a transient systemd user unit, so it outlives the app, then runs
Pollen's own sleep: sleep pose, then the app stops, and the daemon turns the motors off. Replaces Pollen's
``go_to_sleep`` in a personality's tools. If the watcher cannot start, the robot stays awake and says why.
The app runs under the daemon's system service, without a user session, so XDG_RUNTIME_DIR is set explicitly.
"""

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
WAKE_PYTHON = Path(os.environ.get("REACHY_WAKE_PYTHON", "~/venvs/reachy-wake/bin/python")).expanduser()
UNIT = "reachy-wake"


def user_env() -> dict[str, str]:
    """Environment that reaches this user's systemd manager from outside a login session."""
    return {**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}


def start_watcher() -> None:
    """Start the wake watcher unless it is already running; raises if systemd refuses."""
    env = user_env()
    state = subprocess.run(  # noqa: S603 -- fixed arguments
        ["/usr/bin/systemctl", "--user", "is-active", UNIT], env=env, capture_output=True, text=True, timeout=10
    )
    if state.stdout.strip() == "active":
        return
    command = [
        "/usr/bin/systemd-run", "--user", f"--unit={UNIT}", "--collect", f"--working-directory={ROOT}",
        str(WAKE_PYTHON), "-m", "reachy_wake",
    ]
    subprocess.run(command, env=env, check=True, capture_output=True, text=True, timeout=10)  # noqa: S603
    LOG.info("sleep: wake watcher started")


class Sleep(Tool):  # type: ignore[misc]
    """Put Reachy to sleep; the wake word wakes it again."""

    name = "sleep"
    description = (
        "Use when you are sure the user wants Reachy to go to sleep, stop the current app, or end the "
        "conversation. Saying the wake word wakes Reachy again. Do not use for idle turns, sleepy emotions, "
        "silence, or ambiguous requests."
    )
    needs_response = False
    parameters_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Start the watcher, then Pollen's sleep; stay awake if the watcher fails."""
        if deps.go_to_sleep is None:
            return {"error": "sleep is unavailable in this runtime"}
        try:
            await asyncio.to_thread(start_watcher)
        except (OSError, subprocess.SubprocessError) as error:
            detail = getattr(error, "stderr", None) or error
            LOG.warning("sleep: wake watcher failed to start: %s", detail)
            return {"error": f"The wake-word listener could not start ({detail}), so I stayed awake."}
        result: dict[str, Any] = await asyncio.to_thread(deps.go_to_sleep)
        return result
