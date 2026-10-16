"""Tests for the on-device ``weather`` tool, using recorded Open-Meteo replies (Cobham, 2026-10-16, a Friday).
The conversation app's Tool base only exists on the robot, so a stand-in module is registered before import."""

import asyncio
import io
import json
import sys
import types
import urllib.parse
from pathlib import Path
from typing import Any

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
sys.modules.setdefault("reachy_mini_conversation_app.tools.core_tools", _core_tools)

from robot_tools import weather  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
GEOCODE = json.loads((DATA / "weather_geocode_cobham.json").read_text())
FORECAST = json.loads((DATA / "weather_forecast_cobham.json").read_text())


@pytest.fixture
def provider(monkeypatch, tmp_path):
    """Serve recorded replies and record each request's endpoint and query."""
    monkeypatch.setenv("REACHY_TOOLS_STATE_DIR", str(tmp_path))
    calls: list[tuple[str, dict[str, str]]] = []
    replies: dict[str, Any] = {weather.GEOCODING_URL: GEOCODE, weather.FORECAST_URL: FORECAST}

    def urlopen(request, timeout):
        url, _, query = request.full_url.partition("?")
        calls.append((url, dict(urllib.parse.parse_qsl(query))))
        reply = replies[url]
        if isinstance(reply, Exception):
            raise reply
        return io.BytesIO(reply if isinstance(reply, bytes) else json.dumps(reply).encode())

    monkeypatch.setattr(weather.urllib.request, "urlopen", urlopen)
    return types.SimpleNamespace(calls=calls, replies=replies, state=tmp_path)


def test_home_without_coordinates_resolves_surrey_not_kent(provider):
    result = weather.weather_payload()
    assert result["place"] == "Cobham, Surrey, England"
    assert result["source"] == "UK Met Office model via Open-Meteo"
    forecast_query = provider.calls[-1][1]
    assert (forecast_query["latitude"], forecast_query["models"]) == ("51.32997", "ukmo_seamless")


def test_home_with_configured_coordinates_skips_place_lookup(provider):
    (provider.state / "location.json").write_text(json.dumps({"latitude": 51.33, "longitude": -0.41}))
    result = weather.weather_payload(period="now")
    assert [url for url, _ in provider.calls] == [weather.FORECAST_URL]
    assert result["place"] == "Cobham, Surrey"
    assert result["now"]["temperature"] == 10.3
    assert result["now"]["conditions"] == "mainly clear"


def test_named_place_with_county_qualifier(provider):
    assert weather.weather_payload("Cobham, Kent")["place"] == "Cobham, Kent, England"


def test_same_named_towns_without_populations_are_ambiguous(provider):
    provider.replies[weather.GEOCODING_URL] = {
        "results": [
            {
                "name": "Ashford",
                "admin2": "Kent",
                "admin1": "England",
                "country_code": "GB",
                "feature_code": "PPL",
                "latitude": 51.1,
                "longitude": 0.9,
            },
            {
                "name": "Ashford",
                "admin2": "Surrey",
                "admin1": "England",
                "country_code": "GB",
                "feature_code": "PPL",
                "latitude": 51.4,
                "longitude": -0.5,
            },
        ]
    }
    result = weather.weather_payload("Ashford")
    assert result["ambiguous"] is True
    assert result["candidates"] == ["Ashford, Kent, England", "Ashford, Surrey, England"]
    assert [url for url, _ in provider.calls] == [weather.GEOCODING_URL]


def test_dominant_foreign_city_resolves_without_met_office_model(provider):
    provider.replies[weather.GEOCODING_URL] = {
        "results": [
            {
                "name": "Paris",
                "admin1": "Île-de-France",
                "country": "France",
                "country_code": "FR",
                "feature_code": "PPLC",
                "population": 2_138_551,
                "latitude": 48.85,
                "longitude": 2.35,
            },
            {
                "name": "Paris",
                "admin1": "Texas",
                "country": "United States",
                "country_code": "US",
                "feature_code": "PPLA2",
                "population": 24_782,
                "latitude": 33.66,
                "longitude": -95.56,
            },
        ]
    }
    result = weather.weather_payload("Paris")
    assert result["place"] == "Paris, Île-de-France, France"
    assert "models" not in provider.calls[-1][1]


def test_unknown_place_fails_clearly(provider):
    provider.replies[weather.GEOCODING_URL] = {"generationtime_ms": 0.1}
    with pytest.raises(ValueError, match="No town or city"):
        weather.weather_payload("Nowhereville")


@pytest.mark.parametrize(
    ("period", "dates"),
    [("today", ["2026-10-16"]), ("tomorrow", ["2026-10-17"]), ("weekend", ["2026-10-17", "2026-10-18"])],
)
def test_daily_periods(provider, period, dates):
    days = weather.weather_payload(period=period)["days"]
    assert [day["date"] for day in days] == dates
    assert days[0]["weekday"] == {"today": "Friday", "tomorrow": "Saturday", "weekend": "Saturday"}[period]


def test_week_has_seven_days_with_readable_fields(provider):
    days = weather.weather_payload(period="week")["days"]
    assert len(days) == 7
    assert days[0]["conditions"] == "light rain"
    assert (days[0]["high"], days[0]["low"], days[0]["sunset"]) == (15.9, 8.8, "18:06")


def test_hourly_starts_at_the_current_hour(provider):
    hours = weather.weather_payload(period="hourly")["hours"]
    assert len(hours) == weather.HOURLY_HOURS
    assert hours[0]["time"] == "21:00"


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        ("2026-10-16", ["2026-10-17", "2026-10-18"]),
        ("2026-10-17", ["2026-10-17", "2026-10-18"]),
        ("2026-10-18", ["2026-10-18"]),
    ],
)
def test_weekend_from_friday_saturday_and_sunday(today, expected):
    from datetime import date, timedelta

    start = date.fromisoformat(today)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(7)]
    assert [dates[i] for i in weather.weekend_indices(dates)] == expected


def test_fahrenheit_is_requested_from_the_provider(provider):
    assert weather.weather_payload(units="fahrenheit")["temperature_unit"] == "°F"
    assert provider.calls[-1][1]["temperature_unit"] == "fahrenheit"


def test_bad_arguments_are_refused(provider):
    with pytest.raises(ValueError, match="period"):
        weather.weather_payload(period="fortnight")
    with pytest.raises(ValueError, match="units"):
        weather.weather_payload(units="kelvin")


def test_provider_failure_and_oversized_reply_fail_clearly(provider, monkeypatch):
    provider.replies[weather.GEOCODING_URL] = OSError("timed out")
    with pytest.raises(RuntimeError, match="Weather provider unavailable: timed out"):
        weather.weather_payload()
    monkeypatch.setattr(weather, "MAX_BYTES", 100)
    provider.replies[weather.GEOCODING_URL] = GEOCODE
    with pytest.raises(RuntimeError, match="too large"):
        weather.weather_payload()


def test_tool_runs_off_the_event_loop(provider):
    result = asyncio.run(weather.Weather()(None, period="tomorrow"))
    assert result["days"][0]["date"] == "2026-10-17"
