"""Return the robot's configured town-level location for weather and local lookups."""

import json
import math
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

DEFAULT_LOCATION: dict[str, Any] = {
    "place": "Cobham", "region": "Surrey", "country": "United Kingdom", "country_code": "GB",
    "timezone": "Europe/London", "latitude": None, "longitude": None, "provisional": True,
}


def location_path() -> Path:
    """Use external settings, independent of app updates and committed source."""
    directory = Path(os.environ.get("REACHY_TOOLS_STATE_DIR", "~/.config/reachy_tools")).expanduser()
    return directory / "location.json"


def location_payload(path: Path | None = None) -> dict[str, Any]:
    """Read a validated shared location; the initial town is explicitly provisional."""
    path = path or location_path()
    configured = json.loads(path.read_text()) if path.exists() else DEFAULT_LOCATION.copy()
    if not isinstance(configured, dict):
        raise ValueError("Location settings must be a JSON object")
    result = DEFAULT_LOCATION | configured
    if path.exists():
        result["provisional"] = configured.get("provisional", False)
    for name in ("place", "region", "country", "country_code", "timezone"):
        if not isinstance(result[name], str) or not result[name].strip():
            raise ValueError(f"Location setting {name} must be a non-empty string")
    ZoneInfo(result["timezone"])
    latitude, longitude = result["latitude"], result["longitude"]
    if (latitude is None) != (longitude is None):
        raise ValueError("Configure both latitude and longitude, or neither")
    if latitude is not None:
        for name, value, limit in (("latitude", latitude, 90), ("longitude", longitude, 180)):
            if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
                raise ValueError(f"Location {name} must be a finite number")
            if not -limit <= value <= limit:
                raise ValueError(f"Location {name} is outside its valid range")
    result["spoken"] = f"The configured location is {result['place']}, {result['region']}, {result['country']}."
    result["source"] = "configured_file" if path.exists() else "provisional_default"
    return result


class Location(Tool):  # type: ignore[misc]
    """Give every location-dependent tool the same configured place."""

    name = "location"
    description = (
        "Get the configured current location, region, country, timezone and coordinates when configured. "
        "Use this before local weather, local search or local news; never guess the location. "
        "An explicitly requested different place overrides this for that request only."
    )
    parameters_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Return the configured location without making a network request."""
        return location_payload()
