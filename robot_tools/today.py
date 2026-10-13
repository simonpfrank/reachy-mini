"""On-device tool: today's date and time from the robot's clock, phrased for speaking.

Runs inside the conversation app on the robot (external tools folder), no network.
Gives the AI the real date so it stops guessing the year (e.g. searching for "2024").

Usage (inside the app): list "today" in the persona's tools; the app loads this file by name.
"""

from datetime import datetime
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen"
).split()
_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty"}
_ORDINAL_ONES = (
    "zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth "
    "fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth"
).split()
_ORDINAL_TENS = {2: "twentieth", 3: "thirtieth"}
_ROUND_MINUTES = (5, 10, 20, 25)  # said without "minutes": "twenty past", not "twenty minutes past"


def _words(n: int) -> str:
    """Cardinal number words for 0-99."""
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] if ones == 0 else f"{_TENS[tens]}-{_ONES[ones]}"


def _ordinal(n: int) -> str:
    """Ordinal words for 1-31."""
    if n < 20:
        return _ORDINAL_ONES[n]
    tens, ones = divmod(n, 10)
    return _ORDINAL_TENS[tens] if ones == 0 else f"{_TENS[tens]}-{_ORDINAL_ONES[ones]}"


def _year(year: int) -> str:
    """Years as said aloud: 2026 -> 'twenty twenty-six', 2005 -> 'two thousand and five'."""
    century, rest = divmod(year, 100)
    if rest == 0:
        return f"{_words(century // 10)} thousand" if century % 10 == 0 else f"{_words(century)} hundred"
    if century % 10 == 0 and rest < 10:
        return f"{_words(century // 10)} thousand and {_words(rest)}"
    return f"{_words(century)} {_words(rest)}"


def _hour_name(hour24: int) -> str:
    if hour24 == 0:
        return "midnight"
    if hour24 == 12:
        return "midday"
    return _words(hour24 % 12 or 12)


def _part_of_day(hour24: int) -> str:
    if 5 <= hour24 < 12:
        return " in the morning"
    if 12 <= hour24 < 17:
        return " in the afternoon"
    if 17 <= hour24 < 21:
        return " in the evening"
    return " at night"


def spoken_time(now: datetime) -> str:
    """British spoken time: 'twenty past seven in the evening', 'quarter to four in the afternoon', 'midday'."""
    minute = now.minute
    hour24 = now.hour if minute <= 30 else (now.hour + 1) % 24
    hour = _hour_name(hour24)
    gap = minute if minute <= 30 else 60 - minute
    unit = "" if gap in _ROUND_MINUTES else " minutes"
    if minute == 0:
        phrase = hour if hour in ("midnight", "midday") else f"{hour} o'clock"
    elif gap == 15:
        phrase = f"quarter {'past' if minute < 30 else 'to'} {hour}"
    elif minute == 30:
        phrase = f"half past {hour}"
    else:
        phrase = f"{_words(gap)}{unit} {'past' if minute < 30 else 'to'} {hour}"
    return phrase if hour in ("midnight", "midday") else phrase + _part_of_day(hour24)


def spoken_date(now: datetime) -> str:
    """'Tuesday the thirteenth of October, twenty twenty-six'."""
    return f"{now:%A} the {_ordinal(now.day)} of {now:%B}, {_year(now.year)}"


def today_payload(now: datetime) -> dict[str, str]:
    """What the tool returns: a ready-to-say sentence plus the plain values."""
    return {
        "spoken": f"It's {spoken_time(now)} on {spoken_date(now)}.",
        "date": now.strftime("%Y-%m-%d"),
        "weekday": now.strftime("%A"),
        "time_24h": now.strftime("%H:%M"),
        "timezone": now.tzname() or "",
    }


class Today(Tool):  # type: ignore[misc]
    """Tell the AI the real current date and time (robot clock, UK time)."""

    name = "today"
    description = (
        "Get the current date, day of the week and time (UK time, from the robot's clock). Use it before answering "
        "anything about dates or times, and before searching for anything time-sensitive (news, films, events, "
        "'latest', 'this week') so searches use the right year."
    )
    parameters_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, str]:
        """Return today's date and time from the robot's clock."""
        return today_payload(datetime.now().astimezone())
