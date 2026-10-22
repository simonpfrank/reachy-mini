"""On-device tool: what the robot knows about the room from its last scan, in plain anonymous words.

Read-only. It reads the saved picture (``world.json``, made by room_scan) and describes it: the objects seen, roughly
which direction, how sure, how old the information is and how much of the room was covered. Nothing identifying is in
the picture (no names, no faces, no photos), and the reply goes through the reply check like every tool's.
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the app loads tools by path; see reachy_lib
from reachy_lib.replies import checked  # noqa: E402
from reachy_lib.scan_settings import ScanSettings  # noqa: E402
from reachy_lib.world import describe, read_world  # noqa: E402


class RoomView(Tool):  # type: ignore[misc]
    """Tell the model what the last room scan found."""

    name = "room_view"
    description = (
        "Tells you what the robot knows about the room from its last scan: the objects it saw, roughly in which "
        "direction (relative to the robot's own front), how sure it is, how old that information is and how much of "
        "the room the scan covered. Use it when the user asks what is in the room, what is around the robot, or "
        "whether something is there. It only reports what the scan found: it does not know anyone's name, and you "
        "cannot see the photos. If the information is old, missing or incomplete, say so plainly and offer to scan "
        "the room again with room_scan. Never guess beyond what this returns."
    )
    parameters_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    @checked
    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Describe the saved picture of the room; a damaged picture or settings file is reported, not fatal."""
        try:
            world = read_world()
        except ValueError:
            return {
                "state": "unavailable", "objects": [], "possible": [], "older": [], "counts": {},
                "note": "The saved picture of the room is damaged. Say so and offer to scan the room again.",
            }  # fmt: skip
        mistake = ""
        try:
            settings = ScanSettings.load(os.environ)
        except ValueError:
            settings = ScanSettings()
            mistake = " (The scan settings file has a mistake, so the default timings were used.)"
        reply = describe(world, datetime.now(UTC), settings.stale_after_s)
        reply["note"] += mistake
        return reply
