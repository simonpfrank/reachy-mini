"""On-device tool: end the turn without saying anything.

The hosted voice always answers what it hears, so without this the AI announces "staying silent" aloud.
``needs_response = False`` tells the app not to ask the AI to speak after the tool runs, so the turn ends quietly.

Usage (inside the app): list "stay_silent" in the persona's tools; the app loads this file by name.
"""

from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


class StaySilent(Tool):  # type: ignore[misc]
    """End the turn silently when Simon is not talking to the robot."""

    name = "stay_silent"
    description = (
        "Say nothing and end your turn. Use this, with no spoken words, when what you heard was not addressed to you: "
        "a television, radio, game, commentary, adverts, or other people talking among themselves."
    )
    needs_response = False
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Short reason, e.g. 'television' or 'not addressed'."},
        },
        "required": [],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, str]:
        """Return a note for the logs; the app will not prompt a spoken reply."""
        return {"status": "silent", "reason": str(kwargs.get("reason") or "not addressed")}
