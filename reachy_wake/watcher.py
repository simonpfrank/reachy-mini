"""Listen on the shared microphone while the robot sleeps, and start the conversation app on a wake trigger.

Started by the sleep tool (``robot_tools/sleep.py``) as a transient systemd user unit, so it outlives the app.
It waits for the app to stop, listens, starts the app on the first trigger, then exits. Triggers are a list of
callables taking one audio frame and returning a reason or None, so others (loud noise, PIR) can be added later.
Runs in its own venv (``reachy_wake/requirements.txt``); logs: ``journalctl --user -u reachy-wake``.
"""

import json
import logging
import os
import subprocess
import time
import urllib.request
from collections.abc import Callable, Iterator
from typing import IO, Any

import numpy as np
import numpy.typing as npt

LOG = logging.getLogger(__name__)
DAEMON_URL = os.environ.get("REACHY_DAEMON_URL", "http://127.0.0.1:8000")
APP_NAME = "reachy_mini_conversation_app"
MIC = "reachymini_audio_src"  # Pollen's shared (dsnoop) capture device; several readers at once
RATE = 16000
CHANNELS = 2
FRAME = 1280  # 80 ms, the frame size openWakeWord expects
WAKE_MODEL = "hey_mycroft_v0.1"  # temporary built-in word until "hey Reachy" is trained
THRESHOLD = 0.5
STOP_WAIT_S = 120.0
BUSY_STATES = frozenset({"starting", "running", "stopping"})

Frame = npt.NDArray[np.int16]
Trigger = Callable[[Frame], str | None]


def app_running() -> bool:
    """Whether the daemon reports an app starting, running or stopping."""
    url = f"{DAEMON_URL}/api/apps/current-app-status"
    with urllib.request.urlopen(url, timeout=5) as reply:  # noqa: S310 -- fixed local daemon URL
        status = json.load(reply)
    return isinstance(status, dict) and status.get("state") in BUSY_STATES


def wait_for_app_to_stop(timeout_s: float = STOP_WAIT_S) -> bool:
    """Wait until no app holds the robot; False if it is still busy after ``timeout_s``."""
    deadline = time.monotonic() + timeout_s
    while app_running():
        if time.monotonic() >= deadline:
            return False
        time.sleep(1.0)
    return True


def start_app() -> None:
    """Ask the daemon to start the conversation app (it keeps its last-used personality)."""
    url = f"{DAEMON_URL}/api/apps/start-app/{APP_NAME}"
    request = urllib.request.Request(url, method="POST")  # noqa: S310 -- fixed local daemon URL
    with urllib.request.urlopen(request, timeout=30):  # noqa: S310 -- fixed local daemon URL
        pass


def open_mic() -> "subprocess.Popen[bytes]":
    """Raw 16 kHz int16 stereo from the shared capture device."""
    args = ["/usr/bin/arecord", "-q", "-D", MIC, "-f", "S16_LE", "-r", str(RATE), "-c", str(CHANNELS), "-t", "raw"]
    return subprocess.Popen(args, stdout=subprocess.PIPE)  # noqa: S603 -- fixed arguments


def frames(stream: IO[bytes]) -> Iterator[Frame]:
    """Left-channel frames of FRAME samples until the stream ends."""
    size = FRAME * CHANNELS * 2
    while len(chunk := stream.read(size)) == size:
        yield np.frombuffer(chunk, dtype=np.int16).reshape(-1, CHANNELS)[:, 0].copy()


def watch(audio: Iterator[Frame], triggers: list[Trigger]) -> str:
    """The reason given by the first trigger that fires."""
    for frame in audio:
        for trigger in triggers:
            reason = trigger(frame)
            if reason:
                return reason
    raise RuntimeError("the microphone stream ended")


class WakeWord:
    """Trigger: the built-in openWakeWord model scores at least THRESHOLD."""

    def __init__(self, model: Any = None) -> None:
        """Load the bundled model (or use ``model``, which must have ``predict(frame) -> {name: score}``)."""
        if model is None:
            import openwakeword
            from openwakeword.model import Model

            path = next(p for p in openwakeword.get_pretrained_model_paths() if WAKE_MODEL in p)
            model = Model(wakeword_model_paths=[path])
        self._model = model

    def __call__(self, frame: Frame) -> str | None:
        """A reason when the wake word is heard in this frame, else None."""
        score = max(self._model.predict(frame).values())
        return f"wake word ({score:.2f})" if score >= THRESHOLD else None


def run() -> int:
    """Wait for the app to stop, listen, start the app on a trigger. Exit code 0 when the app was started."""
    LOG.info("waiting for the app to stop")
    if not wait_for_app_to_stop():
        LOG.error("the app is still running after %.0f s; not listening", STOP_WAIT_S)
        return 1
    triggers: list[Trigger] = [WakeWord()]
    mic = open_mic()
    LOG.info("listening for the wake word (%s)", WAKE_MODEL)
    try:
        reason = watch(frames(mic.stdout) if mic.stdout else iter(()), triggers)
    finally:
        mic.terminate()
        mic.wait(timeout=5)
    LOG.info("woken by %s; starting %s", reason, APP_NAME)
    start_app()
    return 0
