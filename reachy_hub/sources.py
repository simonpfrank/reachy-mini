"""Read messages from a WebSocket, reconnecting until told to stop.

Two entry points share one connect-and-retry loop:
- ``read_websocket``: JSON messages (app ``/rpc`` events, daemon state stream).
- ``read_text_websocket``: plain text lines (daemon log stream; empty keep-alives skipped).

The robot or app restarting is normal, so a dropped or refused connection is
reported and retried, never raised.

Usage:
    stop = asyncio.Event()
    await read_websocket(APP_RPC_URL, handle_message, show_status, stop)
"""

import asyncio
import json
import logging
from collections.abc import Callable
from functools import partial

import websockets
from websockets.exceptions import WebSocketException

logger = logging.getLogger(__name__)


def _deliver_json(raw: str | bytes, on_message: Callable[[object], None]) -> None:
    try:
        message = json.loads(raw)
    except ValueError:
        logger.debug("Skipping non-JSON message: %.80r", raw)
        return
    on_message(message)


def _deliver_text(raw: str | bytes, on_line: Callable[[str], None]) -> None:
    line = raw.decode(errors="replace") if isinstance(raw, bytes) else raw
    if line.strip():
        on_line(line)


async def _run(
    url: str,
    deliver: Callable[[str | bytes], None],
    on_status: Callable[[str], None],
    stop: asyncio.Event,
    retry_s: float,
) -> None:
    while not stop.is_set():
        try:
            async with websockets.connect(url, open_timeout=5) as connection:
                on_status("connected")
                async for raw in connection:
                    deliver(raw)
                    if stop.is_set():
                        return
            on_status("disconnected: closed")
        except (OSError, WebSocketException, TimeoutError) as exc:
            on_status(f"disconnected: {type(exc).__name__}")
        try:
            await asyncio.wait_for(stop.wait(), retry_s)
        except TimeoutError:
            pass


async def read_websocket(
    url: str,
    on_message: Callable[[object], None],
    on_status: Callable[[str], None],
    stop: asyncio.Event,
    retry_s: float = 2.0,
) -> None:
    """Deliver each JSON message from ``url`` to ``on_message`` until ``stop`` is set.

    Args:
        url: WebSocket URL, e.g. ``ws://192.168.0.15:7860/rpc``.
        on_message: Called with each decoded JSON message.
        on_status: Called with "connected" or "disconnected: <reason>".
        stop: Set it to end the loop.
        retry_s: Seconds to wait before reconnecting.
    """
    await _run(url, partial(_deliver_json, on_message=on_message), on_status, stop, retry_s)


async def read_text_websocket(
    url: str,
    on_line: Callable[[str], None],
    on_status: Callable[[str], None],
    stop: asyncio.Event,
    retry_s: float = 2.0,
) -> None:
    """Deliver each non-empty text line from ``url`` to ``on_line`` until ``stop`` is set.

    Args:
        url: WebSocket URL, e.g. ``ws://192.168.0.15:8000/api/logs/ws/daemon``.
        on_line: Called with each non-empty line.
        on_status: Called with "connected" or "disconnected: <reason>".
        stop: Set it to end the loop.
        retry_s: Seconds to wait before reconnecting.
    """
    await _run(url, partial(_deliver_text, on_line=on_line), on_status, stop, retry_s)
