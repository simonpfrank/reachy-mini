"""reachy_wake.watcher: wait for the app to stop, listen on the mic, start the app on a wake trigger."""

import io
import json
import types
from typing import Any

import numpy as np
import pytest

from reachy_wake import watcher


def stereo(*frames_left: int) -> bytes:
    """Stereo int16 audio, one watcher frame per value (left channel = value, right = -1)."""
    out = bytearray()
    for value in frames_left:
        pairs = np.empty((watcher.FRAME, 2), dtype=np.int16)
        pairs[:, 0], pairs[:, 1] = value, -1
        out += pairs.tobytes()
    return bytes(out)


class Reply(io.BytesIO):
    def __enter__(self) -> "Reply":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def daemon(monkeypatch, statuses: list[Any], requests: list[Any] | None = None) -> None:
    """Fake daemon: each GET returns the next status; POSTs are recorded."""
    replies = iter(statuses)

    def urlopen(request, timeout=0):
        if getattr(request, "method", "GET") == "POST":
            (requests if requests is not None else []).append(request.full_url)
            return Reply(b"{}")
        return Reply(json.dumps(next(replies)).encode())

    monkeypatch.setattr(watcher.urllib.request, "urlopen", urlopen)


@pytest.mark.parametrize(
    ("status", "busy"),
    [({"state": "running"}, True), ({"state": "starting"}, True), ({"state": "stopping"}, True),
     ({"state": "done"}, False), ({"state": "error"}, False), (None, False)],
)
def test_app_is_busy_while_starting_running_or_stopping(monkeypatch, status, busy):
    daemon(monkeypatch, [status])
    assert watcher.app_running() is busy


def test_waits_until_the_app_has_stopped(monkeypatch):
    daemon(monkeypatch, [{"state": "running"}, {"state": "stopping"}, None])
    monkeypatch.setattr(watcher.time, "sleep", lambda _s: None)
    assert watcher.wait_for_app_to_stop(timeout_s=60) is True


def test_gives_up_if_the_app_never_stops(monkeypatch):
    daemon(monkeypatch, [{"state": "running"}] * 3)
    monkeypatch.setattr(watcher.time, "sleep", lambda _s: None)
    assert watcher.wait_for_app_to_stop(timeout_s=0) is False


def test_start_app_posts_to_the_daemon(monkeypatch):
    posted: list[str] = []
    daemon(monkeypatch, [], posted)
    watcher.start_app()
    assert posted == [f"{watcher.DAEMON_URL}/api/apps/start-app/{watcher.APP_NAME}"]


def test_frames_are_the_left_channel_and_a_partial_tail_is_dropped():
    stream = io.BytesIO(stereo(3, 7) + b"\x00" * 10)
    got = list(watcher.frames(stream))
    assert [len(f) for f in got] == [watcher.FRAME, watcher.FRAME]
    assert got[0].dtype == np.int16 and set(got[0]) == {3} and set(got[1]) == {7}


def test_watch_returns_the_first_trigger_reason():
    seen: list[int] = []

    def quiet(frame: np.ndarray) -> str | None:
        seen.append(int(frame[0]))
        return None

    def loud(frame: np.ndarray) -> str | None:
        return "loud" if frame[0] == 9 else None

    assert watcher.watch(watcher.frames(io.BytesIO(stereo(1, 9, 2))), [quiet, loud]) == "loud"
    assert seen == [1, 9]


def test_watch_fails_when_the_mic_stream_ends():
    with pytest.raises(RuntimeError, match="microphone"):
        watcher.watch(watcher.frames(io.BytesIO(stereo(1))), [lambda _f: None])


def test_wake_word_fires_at_the_threshold():
    scores = iter([0.2, watcher.THRESHOLD])
    model = types.SimpleNamespace(predict=lambda _frame: {"hey_mycroft_v0.1": next(scores)})
    wake = watcher.WakeWord(model)
    frame = np.zeros(watcher.FRAME, dtype=np.int16)
    assert wake(frame) is None
    assert wake(frame) == f"wake word ({watcher.THRESHOLD:.2f})"


def test_run_starts_the_app_after_a_wake_word(monkeypatch):
    started: list[bool] = []
    mic = types.SimpleNamespace(stdout=io.BytesIO(stereo(0, 5)), terminate=lambda: None, wait=lambda timeout=0: 0)
    monkeypatch.setattr(watcher, "wait_for_app_to_stop", lambda timeout_s=0: True)
    monkeypatch.setattr(watcher, "WakeWord", lambda: (lambda frame: "wake word" if frame[0] == 5 else None))
    monkeypatch.setattr(watcher, "open_mic", lambda: mic)
    monkeypatch.setattr(watcher, "start_app", lambda: started.append(True))
    assert watcher.run() == 0 and started == [True]


def test_run_does_nothing_if_the_app_keeps_running(monkeypatch):
    monkeypatch.setattr(watcher, "wait_for_app_to_stop", lambda timeout_s=0: False)
    monkeypatch.setattr(watcher, "start_app", lambda: pytest.fail("must not start the app"))
    assert watcher.run() == 1


def test_mic_is_read_from_the_shared_device_without_a_shell(monkeypatch):
    calls: list[Any] = []
    monkeypatch.setattr(watcher.subprocess, "Popen", lambda args, **kwargs: calls.append((args, kwargs)))
    watcher.open_mic()
    args, kwargs = calls[0]
    assert args[0].endswith("arecord") and watcher.MIC in args and "shell" not in kwargs
