"""On-device tool: weather forecast from the UK Met Office model via Open-Meteo (no key).

Replaces Pollen's built-in weather tool, which only gives today's high/low. Uses the configured home
location (location.json, shared with the location tool) unless the user names another place.
Standard library only; HTTPS to two fixed Open-Meteo hosts with a timeout and a response-size cap.
"""

import asyncio
import json
import logging
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the app loads tools by path; see reachy_lib
from reachy_lib.storage import state_dir  # noqa: E402

LOG = logging.getLogger(__name__)
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
TIMEOUT_S = 10
MAX_BYTES = 2_000_000
PERIODS = ("now", "today", "tomorrow", "hourly", "weekend", "week")
HOURLY_HOURS = 12
DOMINANT_POPULATION = 10  # an unqualified name resolves to the top match only if it is this many times larger
HOME = {"place": "Cobham", "region": "Surrey", "country_code": "GB", "latitude": None, "longitude": None}

# WMO weather interpretation codes, as used by Open-Meteo.
CONDITIONS = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "freezing fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "light freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light showers",
    81: "showers",
    82: "violent showers",
    85: "light snow showers",
    86: "snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with heavy hail",
}
CURRENT = "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,wind_gusts_10m,precipitation"
HOURLY = "temperature_2m,precipitation_probability,weather_code,wind_speed_10m"
DAILY = (
    "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,"
    "wind_speed_10m_max,wind_gusts_10m_max,sunrise,sunset"
)


def get_json(url: str, params: dict[str, Any]) -> Any:
    """GET one of the fixed Open-Meteo endpoints; fail clearly on errors, slowness or oversized replies."""
    if url not in (FORECAST_URL, GEOCODING_URL):
        raise ValueError(f"Unexpected weather endpoint {url}")
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "reachy-tools"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 -- fixed HTTPS host
            body = response.read(MAX_BYTES + 1)
    except OSError as error:
        raise RuntimeError(f"Weather provider unavailable: {error}") from error
    if len(body) > MAX_BYTES:
        raise RuntimeError("Weather provider reply was too large")
    return json.loads(body)


def home_location(path: Path | None = None) -> dict[str, Any]:
    """The configured home place, read from the same file as the location tool."""
    path = path or state_dir() / "location.json"
    configured = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(configured, dict):
        raise ValueError("Location settings must be a JSON object")
    return HOME | {key: configured[key] for key in HOME if key in configured}


def _label(result: dict[str, Any]) -> str:
    parts = [result.get("name"), result.get("admin2"), result.get("admin1")]
    if result.get("country_code") != "GB":
        parts.append(result.get("country"))
    return ", ".join(dict.fromkeys(p for p in parts if p))


def _matches(result: dict[str, Any], qualifier: str) -> bool:
    fields = ("admin1", "admin2", "admin3", "admin4", "country", "country_code")
    return any(qualifier.lower() in str(result.get(field) or "").lower() for field in fields)


def resolve_place(place: str | None, home: dict[str, Any]) -> dict[str, Any]:
    """Coordinates and a spoken label for the place, or candidates when the name is ambiguous."""
    if place is None or not place.strip():
        if home["latitude"] is not None and home["longitude"] is not None:
            label = f"{home['place']}, {home['region']}"
            return {
                "label": label,
                "latitude": home["latitude"],
                "longitude": home["longitude"],
                "country_code": home["country_code"],
            }
        place = f"{home['place']}, {home['region']}"
    name, *qualifiers = [part.strip() for part in place.split(",") if part.strip()]
    if not qualifiers and name.lower() == str(home["place"]).lower():
        qualifiers = [home["region"]]
    results = get_json(GEOCODING_URL, {"name": name, "count": 10, "language": "en", "format": "json"})
    results = [r for r in results.get("results", []) if r.get("feature_code", "").startswith("PPL")]
    for qualifier in qualifiers:
        results = [r for r in results if _matches(r, qualifier)]
    if not qualifiers:
        nearby = [r for r in results if r.get("country_code") == home["country_code"]]
        results = nearby or results
    if not results:
        raise ValueError(f"No town or city called {place!r} was found")
    first, *others = results
    population = first.get("population") or 0
    if others and (not population or population < DOMINANT_POPULATION * max(r.get("population") or 0 for r in others)):
        return {"ambiguous": True, "candidates": [_label(r) for r in results[:5]]}
    return {
        "label": _label(first),
        "latitude": first["latitude"],
        "longitude": first["longitude"],
        "country_code": first.get("country_code"),
    }


def _condition(code: Any) -> str | None:
    return CONDITIONS.get(code, f"weather code {code}") if code is not None else None


def _days(daily: dict[str, list[Any]], indices: list[int]) -> list[dict[str, Any]]:
    return [
        {
            "date": daily["time"][i],
            "weekday": date.fromisoformat(daily["time"][i]).strftime("%A"),
            "conditions": _condition(daily["weather_code"][i]),
            "high": daily["temperature_2m_max"][i],
            "low": daily["temperature_2m_min"][i],
            "rain_chance_percent": daily["precipitation_probability_max"][i],
            "rain_mm": daily["precipitation_sum"][i],
            "wind_mph": daily["wind_speed_10m_max"][i],
            "gusts_mph": daily["wind_gusts_10m_max"][i],
            "sunrise": daily["sunrise"][i][-5:] if daily["sunrise"][i] else None,
            "sunset": daily["sunset"][i][-5:] if daily["sunset"][i] else None,
        }
        for i in indices
    ]


def weekend_indices(dates: list[str]) -> list[int]:
    """This weekend: Saturday and Sunday, or just Sunday when asked on a Sunday."""
    today = date.fromisoformat(dates[0])
    if today.weekday() == 6:
        wanted = {today.isoformat()}
    else:
        saturday = today + timedelta(days=(5 - today.weekday()) % 7)
        wanted = {saturday.isoformat(), (saturday + timedelta(days=1)).isoformat()}
    return [i for i, day in enumerate(dates) if day in wanted]


def forecast_payload(forecast: dict[str, Any], period: str) -> dict[str, Any]:
    """Select the requested period from one Open-Meteo forecast response."""
    current, hourly, daily = forecast["current"], forecast["hourly"], forecast["daily"]
    if period == "now":
        return {
            "now": {
                "conditions": _condition(current["weather_code"]),
                "temperature": current["temperature_2m"],
                "feels_like": current["apparent_temperature"],
                "wind_mph": current["wind_speed_10m"],
                "gusts_mph": current["wind_gusts_10m"],
                "rain_mm": current["precipitation"],
            }
        }
    if period == "hourly":
        hour = current["time"][:13] + ":00"
        start = hourly["time"].index(hour) if hour in hourly["time"] else 0
        return {
            "hours": [
                {
                    "time": hourly["time"][i][-5:],
                    "conditions": _condition(hourly["weather_code"][i]),
                    "temperature": hourly["temperature_2m"][i],
                    "rain_chance_percent": hourly["precipitation_probability"][i],
                    "wind_mph": hourly["wind_speed_10m"][i],
                }
                for i in range(start, min(start + HOURLY_HOURS, len(hourly["time"])))
            ]
        }
    indices = {
        "today": [0],
        "tomorrow": [1],
        "weekend": weekend_indices(daily["time"]),
        "week": list(range(len(daily["time"]))),
    }[period]
    return {"days": _days(daily, indices)}


def weather_payload(place: str | None = None, period: str = "today", units: str = "celsius") -> dict[str, Any]:
    """Resolve the place, fetch one forecast and return the requested period."""
    if period not in PERIODS:
        raise ValueError(f"period must be one of {', '.join(PERIODS)}")
    if units not in ("celsius", "fahrenheit"):
        raise ValueError("units must be celsius or fahrenheit")
    resolved = resolve_place(place, home_location())
    if resolved.get("ambiguous"):
        return resolved | {"spoken": "There is more than one place with that name; ask which one is meant."}
    uk = resolved["country_code"] == "GB"
    params = {
        "latitude": resolved["latitude"],
        "longitude": resolved["longitude"],
        "current": CURRENT,
        "hourly": HOURLY,
        "daily": DAILY,
        "forecast_days": 7,
        "timezone": "auto",
        "wind_speed_unit": "mph",
        "temperature_unit": units,
    }
    if uk:
        params["models"] = "ukmo_seamless"
    forecast = get_json(FORECAST_URL, params)
    LOG.info("weather place=%s period=%s", resolved["label"], period)
    return {
        "place": resolved["label"],
        "period": period,
        "temperature_unit": "°C" if units == "celsius" else "°F",
        "source": "UK Met Office model via Open-Meteo" if uk else "Open-Meteo best available model",
        "forecast_time": forecast["current"]["time"],
        "timezone": forecast.get("timezone"),
        "warnings": "Official weather warnings are not included in this forecast.",
    } | forecast_payload(forecast, period)


class Weather(Tool):  # type: ignore[misc]
    """Forecast for home or a named place: now, today, tomorrow, hourly, weekend or the week."""

    name = "weather"
    description = (
        "Get the weather forecast. Omit place for home (the configured location); give a place such as "
        "'Edinburgh' or 'Cobham, Kent' when the user names one (that does not change home). Periods: now, "
        "today, tomorrow, hourly (next 12 hours), weekend, week (7 days). If the result is ambiguous, ask "
        "which candidate the user means. Say the place you looked up."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "place": {"type": "string", "description": "Town or city, optionally with county or country."},
            "period": {"type": "string", "enum": list(PERIODS), "description": "Defaults to today."},
            "units": {"type": "string", "enum": ["celsius", "fahrenheit"], "description": "Defaults to celsius."},
        },
        "required": [],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Fetch the forecast without blocking the conversation loop."""
        try:
            return await asyncio.to_thread(
                weather_payload, kwargs.get("place"), kwargs.get("period") or "today", kwargs.get("units") or "celsius"
            )
        except Exception as error:
            LOG.warning("weather failed: %s", error)
            raise
