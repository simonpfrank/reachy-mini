"""Try the voice tracker on the robot: ``python -m reachy_hub.track``.

Default is a dry run: it reads the sound direction and prints what it WOULD do. With ``--live`` it turns the
head (head only, capped) through the daemon's move command, and checks the first turn to learn whether the sound
direction is relative to the head or to the base. Live mode refuses to run while a robot app is running, because
the app's own movement code would fight it; stop the conversation app first.

Usage:
    .venv/bin/python -m reachy_hub.track --host 192.168.0.15 --seconds 60
    .venv/bin/python -m reachy_hub.track --host 192.168.0.15 --seconds 60 --live
"""

import argparse
import asyncio
import json
import math
import time
from typing import Any

import httpx
import websockets

from reachy_hub.tracker import SoundSample, TurnDecision, VoiceTracker

STATE_QUERY = "frequency=20&with_doa=true&with_head_pose=true&with_body_yaw=true&with_antenna_positions=false"
MOVE_SECONDS = 1.5
MIN_HEAD_CHANGE_DEG = 15.0  # the head must have moved this much for a frame check to mean anything
SAME_SOURCE_TOLERANCE_DEG = 25.0  # a reading further than this from both predictions is a different source


def sample_from_state(state: dict[str, Any], now: float) -> tuple[SoundSample, float]:
    """Turn a daemon state message into a sound sample and the head's turn relative to the body (degrees, left +)."""
    doa = state.get("doa") or {}
    angle = doa.get("angle")
    head_deg = math.degrees(state["head_pose"]["yaw"]) - math.degrees(state.get("body_yaw") or 0.0)
    sample = SoundSample(
        now, math.degrees(angle) if isinstance(angle, int | float) else None, bool(doa.get("speech_detected"))
    )
    return sample, head_deg


def goto_body(target_head_deg: float, body_yaw_deg: float, duration_s: float) -> dict[str, Any]:
    """Build the daemon's move request: head turns to ``target_head_deg`` from the body; the body stays put."""
    heading = math.radians(body_yaw_deg + target_head_deg)  # the daemon takes the head's heading from the base
    head_pose = {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": heading}
    return {"head_pose": head_pose, "body_yaw": math.radians(body_yaw_deg), "duration": duration_s}


def frame_verdict(before_deg: float, after_deg: float, head_change_deg: float) -> str:
    """Did the reading of one source follow the head? Compare it with what each frame predicts.

    Head-relative: the reading moves by the head's own turn (left turns raise it). Base-relative: it stays put.
    If the reading matches neither (probably a different source) or the head hardly moved, there is no verdict.
    """
    if abs(head_change_deg) < MIN_HEAD_CHANGE_DEG:
        return "inconclusive"
    error_head = abs(after_deg - (before_deg + head_change_deg))
    error_base = abs(after_deg - before_deg)
    if min(error_head, error_base) > SAME_SOURCE_TOLERANCE_DEG:
        return "inconclusive"
    return "head-relative" if error_head < error_base else "base-relative"


async def _guard_live(client: httpx.AsyncClient, allow_app: bool) -> None:
    status = (await client.get("/api/daemon/status")).json()
    if status["backend_status"]["motor_control_mode"] != "enabled":
        raise SystemExit("Motors are not enabled: refusing to move the head.")
    app = (await client.get("/api/apps/current-app-status")).json()
    if app and not allow_app:
        raise SystemExit(f"A robot app is running ({app['info']['name']}): stop it first, or pass --allow-app.")


async def _move(client: httpx.AsyncClient, decision: TurnDecision, body_deg: float) -> None:
    await client.post("/api/move/goto", json=goto_body(decision.target_head_deg, body_deg, MOVE_SECONDS))


def _report(decision: TurnDecision, live: bool) -> None:
    side = "left" if decision.offset_deg > 0 else "right"
    note = " (capped)" if decision.clamped else ""
    verb = "TURN" if live else "WOULD turn"
    print(
        f"[{decision.t:6.1f}s] {verb} head to {decision.target_head_deg:+.0f} deg: source {decision.source_deg:.0f} "
        f"deg, {abs(decision.offset_deg):.0f} deg to the {side}{note}",
        flush=True,
    )


async def run(host: str, live: bool, seconds: float, allow_app: bool) -> None:
    """Read the state stream for ``seconds`` and print (or carry out) the tracker's decisions."""
    tracker = VoiceTracker()
    async with httpx.AsyncClient(base_url=f"http://{host}:8000", timeout=10) as client:
        if live:
            await _guard_live(client, allow_app)
        start = time.time()
        try:
            await _track(client, tracker, host, live, seconds, start)
        finally:
            if live:  # always hand the head back, even if the run is interrupted
                await client.post("/api/move/goto", json=goto_body(0.0, 0.0, MOVE_SECONDS))
                print("Head returned to centre.", flush=True)


async def _track(
    client: httpx.AsyncClient, tracker: VoiceTracker, host: str, live: bool, seconds: float, start: float
) -> None:
    """The tracking loop: read the sound stream, feed the tracker, carry out its decisions."""
    pending: tuple[float, float, float] | None = None  # (check time, source angle before, head before)
    checked = False
    next_note = 0.0
    async with websockets.connect(f"ws://{host}:8000/api/state/ws/full?{STATE_QUERY}") as ws:
        while time.time() - start < seconds:
            state = json.loads(await asyncio.wait_for(ws.recv(), 5))
            now = time.time() - start
            sample, head_deg = sample_from_state(state, now)
            decision = tracker.feed(sample, head_deg)
            if now >= next_note:
                next_note = now + 2.0
                print(f"[{now:5.1f}s] {tracker.note}", flush=True)
            if decision:
                _report(decision, live)
                if live:
                    await _move(client, decision, math.degrees(state.get("body_yaw") or 0.0))
                    if not checked and pending is None:
                        pending = (now + MOVE_SECONDS + 1.5, decision.source_deg, head_deg)
            if pending and now >= pending[0] and sample.speech and sample.angle_deg is not None:
                before, after = pending[1], sample.angle_deg
                moved = head_deg - pending[2]
                verdict = frame_verdict(before, after, moved)
                note = f"{before:.0f} -> {after:.0f} deg after a {moved:+.0f} deg head move"
                print(f"          frame check: {note} = {verdict}", flush=True)
                pending, checked = None, True


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="192.168.0.15")
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--live", action="store_true", help="really move the head (default: dry run)")
    parser.add_argument("--allow-app", action="store_true", help="live mode even while a robot app runs (not advised)")
    args = parser.parse_args()
    asyncio.run(run(args.host, args.live, args.seconds, args.allow_app))


if __name__ == "__main__":
    main()
