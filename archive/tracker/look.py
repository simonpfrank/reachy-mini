"""Experiment: look at whoever the conversation app hears speaking (roadmap 3a, third try).

The app's hosted detector says WHEN someone speaks (reliable at normal volume); the chip says FROM WHERE, but only
in the moments its own speech flag is on. So: when the app reports ``user_speech_started``, collect the chip's
flagged directions, and 0.8 s in (or at ``user_speech_stopped`` if sooner) turn toward their median. Beyond the
head's reach the body turns too. Once per utterance. Runs WITH the app (the chip hears far better then).

Usage:
    .venv/bin/python -m reachy_hub.look --seconds 60          # dry run: prints what it would do
    .venv/bin/python -m reachy_hub.look --seconds 60 --live   # moves the head and body
"""

import argparse
import asyncio
import math
import statistics
import time
from typing import Any

import httpx

from reachy_hub.sources import read_websocket
from reachy_hub.track import MOVE_SECONDS, goto_body

STATE_QUERY = "frequency=20&with_doa=true&with_head_pose=true&with_body_yaw=true&with_antenna_positions=false"
REACT_AFTER_S = 0.8
MIN_READINGS = 2
HEAD_REACH_DEG = 35.0
BODY_LIMITS_DEG = (-125.0, 140.0)  # measured cable limits, with a margin


def plan_turn(bearing_deg: float) -> tuple[float, float]:
    """Split a bearing from the base (left +) into (head turn from body, body yaw), head first."""
    if abs(bearing_deg) <= HEAD_REACH_DEG:
        return bearing_deg, 0.0
    head = math.copysign(HEAD_REACH_DEG, bearing_deg)
    body = max(BODY_LIMITS_DEG[0], min(BODY_LIMITS_DEG[1], bearing_deg - head))
    return head, body


class Looker:
    """Joins the two feeds: chip readings (state) and app speech events (rpc)."""

    def __init__(self, client: httpx.AsyncClient, live: bool) -> None:
        self._client, self._live = client, live
        self._start = time.time()
        self._speech_since: float | None = None
        self._readings: list[float] = []  # bearings from the base during the current utterance
        self._acted = False

    def _now(self) -> float:
        return time.time() - self._start

    def on_state(self, state: object) -> None:
        if not isinstance(state, dict) or self._speech_since is None:
            return
        doa: dict[str, Any] = state.get("doa") or {}
        if doa.get("speech_detected") and isinstance(doa.get("angle"), int | float):
            heading = math.degrees(state["head_pose"]["yaw"])  # head heading from the base, body included
            self._readings.append(heading + 90.0 - math.degrees(doa["angle"]))
        if not self._acted and self._now() - self._speech_since >= REACT_AFTER_S:
            self._decide("0.8 s into speech")

    def on_app(self, message: object) -> None:
        reason = message.get("params", {}).get("reason") if isinstance(message, dict) else None
        if reason == "user_speech_started":
            self._speech_since, self._readings, self._acted = self._now(), [], False
            print(f"[{self._now():5.1f}s] app: speech started", flush=True)
        elif reason == "user_speech_stopped" and self._speech_since is not None:
            if not self._acted:
                self._decide("speech stopped")
            print(f"[{self._now():5.1f}s] app: speech stopped", flush=True)
            self._speech_since = None

    def _decide(self, why: str) -> None:
        if len(self._readings) < MIN_READINGS:
            print(f"[{self._now():5.1f}s] {why}: only {len(self._readings)} flagged readings, waiting", flush=True)
            if why == "speech stopped":
                self._acted = True
            return
        self._acted = True
        bearing = statistics.median(self._readings)
        head, body = plan_turn(bearing)
        verb = "TURN" if self._live else "WOULD turn"
        print(f"[{self._now():5.1f}s] {why}: {len(self._readings)} readings, median {bearing:+.0f} deg -> "
              f"{verb} body {body:+.0f}, head {head:+.0f}", flush=True)
        if self._live:
            asyncio.get_running_loop().create_task(
                self._client.post("/api/move/goto", json=goto_body(head, body, MOVE_SECONDS))
            )


async def run(host: str, seconds: float, live: bool) -> None:
    """Listen to both feeds for ``seconds``; in live mode, turn and finally return to centre."""
    stop = asyncio.Event()
    async with httpx.AsyncClient(base_url=f"http://{host}:8000", timeout=10) as client:
        looker = Looker(client, live)
        feeds = [
            read_websocket(f"ws://{host}:7860/rpc", looker.on_app, lambda s: print("app:", s, flush=True), stop),
            read_websocket(f"ws://{host}:8000/api/state/ws/full?{STATE_QUERY}", looker.on_state,
                           lambda s: print("chip:", s, flush=True), stop),
        ]
        tasks = [asyncio.create_task(feed) for feed in feeds]
        try:
            await asyncio.sleep(seconds)
        finally:
            stop.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            if live:
                await client.post("/api/move/goto", json=goto_body(0.0, 0.0, MOVE_SECONDS))
                print("Returned to centre.", flush=True)


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="192.168.0.15")
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--live", action="store_true", help="really move (default: dry run)")
    args = parser.parse_args()
    asyncio.run(run(args.host, args.seconds, args.live))


if __name__ == "__main__":
    main()
