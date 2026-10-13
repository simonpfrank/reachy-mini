import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from reachy_hub import sources


class FakeConnection:
    """Stands in for a websockets connection: yields the given raw messages then closes."""

    def __init__(self, messages: list[str]) -> None:
        self.messages = messages

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def __aiter__(self) -> AsyncIterator[str]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[str]:
        for message in self.messages:
            yield message


def _run(connect: Any, monkeypatch: pytest.MonkeyPatch, stop_after_status: int) -> tuple[list[object], list[str]]:
    """Run read_websocket with a fake connect; stop after N status reports."""
    monkeypatch.setattr(sources.websockets, "connect", connect)
    received: list[object] = []
    statuses: list[str] = []
    stop = asyncio.Event()

    def on_status(status: str) -> None:
        statuses.append(status)
        if len(statuses) >= stop_after_status:
            stop.set()

    asyncio.run(sources.read_websocket("ws://x", received.append, on_status, stop, retry_s=0))
    return received, statuses


def test_delivers_decoded_json_in_order_and_reports_status(monkeypatch: pytest.MonkeyPatch) -> None:
    connect = lambda url, **kw: FakeConnection(['{"a": 1}', '{"b": 2}'])  # noqa: E731
    received, statuses = _run(connect, monkeypatch, stop_after_status=2)
    assert received == [{"a": 1}, {"b": 2}]
    assert statuses == ["connected", "disconnected: closed"]


def test_non_json_message_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    connect = lambda url, **kw: FakeConnection(["not json", '{"ok": true}'])  # noqa: E731
    received, _ = _run(connect, monkeypatch, stop_after_status=2)
    assert received == [{"ok": True}]


def test_refused_connection_is_reported_and_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(url: str, **kw: object) -> FakeConnection:
        raise ConnectionRefusedError

    _, statuses = _run(refuse, monkeypatch, stop_after_status=3)
    assert statuses == ["disconnected: ConnectionRefusedError"] * 3


def test_text_mode_delivers_lines_and_skips_keepalives(monkeypatch: pytest.MonkeyPatch) -> None:
    connect = lambda url, **kw: FakeConnection(["line one", "", "line two"])  # noqa: E731
    monkeypatch.setattr(sources.websockets, "connect", connect)
    received: list[str] = []
    stop = asyncio.Event()
    statuses: list[str] = []

    def on_status(status: str) -> None:
        statuses.append(status)
        if len(statuses) >= 2:
            stop.set()

    asyncio.run(sources.read_text_websocket("ws://x", received.append, on_status, stop, retry_s=0))
    assert received == ["line one", "line two"]


def test_returns_immediately_when_already_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    def must_not_connect(url: str, **kw: object) -> FakeConnection:
        raise AssertionError("should not connect")

    monkeypatch.setattr(sources.websockets, "connect", must_not_connect)
    stop = asyncio.Event()
    stop.set()
    asyncio.run(sources.read_websocket("ws://x", print, print, stop, retry_s=10))
