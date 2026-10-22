"""The one check every tool reply passes through, so raw sensor data and private paths cannot reach the LLM.

A reply may hold only plain data: text, numbers, true/false, nothing, and lists and dictionaries of those (with text
keys). Anything else is refused: bytes, arrays, files, objects. Text is refused if it looks like encoded image data
or names one of the private folders (photos, scans, keys). A refusal says what rule was broken and never repeats the
data. This is an allow-list: a new kind of value is blocked until someone decides it is safe and adds it here.

Usage: put ``@checked`` above a tool's ``async def __call__``; a test fails for any tool that lacks it.
"""

import functools
import re
from collections.abc import Awaitable, Callable
from typing import Any

from .keys import keys_dir
from .storage import camera_dir, scan_dir

MAX_CHARS = 100_000  # the longest article text we send is 8,000; this stops a whole file or dump going through
MAX_DEPTH = 12
BASE64_RUN = re.compile(r"[A-Za-z0-9+/=]{200,}")  # a long unbroken run with no spaces or punctuation: encoded data
IMAGE_PREFIXES = ("data:image", "/9j/", "iVBOR")  # a data URL, a base64 JPEG, a base64 PNG
MEDIA_KEY = re.compile(r"b64", re.IGNORECASE)  # Pollen's camera tool puts its photo under "b64_im"
PRIVATE_PATH_PARTS = (".local/share/reachy-tools", ".config/reachy_tools/keys")


class ReplyRefused(ValueError):
    """A tool tried to give the LLM something it must not have."""


def check_reply(reply: Any) -> Any:
    """Return ``reply`` unchanged if it is safe to give the LLM.

    Args:
        reply: What a tool is about to return.

    Returns:
        The same reply.

    Raises:
        ReplyRefused: It holds something that is not plain data, looks like encoded media, names a private folder,
            or is too large. The message names the rule, never the data.
    """
    private = [str(camera_dir()), str(scan_dir()), str(keys_dir()), *PRIVATE_PATH_PARTS]
    size = _walk(reply, private, 0)
    if size > MAX_CHARS:
        raise ReplyRefused(f"The reply is too large ({size} characters)")
    return reply


def checked(call: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Decorator for a tool's ``async def __call__``: its reply goes through ``check_reply`` before the LLM sees it."""

    @functools.wraps(call)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return check_reply(await call(*args, **kwargs))

    return wrapper


def _walk(value: Any, private: list[str], depth: int) -> int:
    """Check ``value`` and everything inside it; returns the number of characters of text it holds."""
    if depth > MAX_DEPTH:
        raise ReplyRefused("The reply is nested too deeply")
    if value is None or isinstance(value, bool | int | float):
        return 0
    if isinstance(value, str):
        _check_text(value, private)
        return len(value)
    if isinstance(value, dict):
        size = 0
        for key, item in value.items():
            if not isinstance(key, str):
                raise ReplyRefused("A dictionary key in the reply is not text")
            if MEDIA_KEY.search(key):
                raise ReplyRefused("A key in the reply looks like encoded media (b64)")
            size += len(key) + _walk(item, private, depth + 1)
        return size
    if isinstance(value, list | tuple):
        return sum(_walk(item, private, depth + 1) for item in value)
    raise ReplyRefused(f"A value of type {type(value).__name__} is not plain data")


def _check_text(text: str, private: list[str]) -> None:
    if text.startswith(IMAGE_PREFIXES) or BASE64_RUN.search(text):
        raise ReplyRefused("Text in the reply looks like encoded image data")
    if any(fragment in text for fragment in private):
        raise ReplyRefused("Text in the reply names a private folder")
