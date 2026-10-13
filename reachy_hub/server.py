"""Web server for the dashboard: one page plus a JSON snapshot, fed by the live sources.

Usage:
    app = create_app(Store(), robot_host="192.168.0.15")
    uvicorn.run(app, host="127.0.0.1", port=8710)
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse

from reachy_hub.sources import read_text_websocket, read_websocket
from reachy_hub.store import Store

STATIC = Path(__file__).parent / "static"
APP_RPC_PORT = 7860
DAEMON_PORT = 8000
STATE_QUERY = "frequency=5&with_doa=true&with_imu=true"
# Taps last a few hundredths of a second, so the IMU needs its own fast, IMU-only feed.
IMU_QUERY = "frequency=50&with_imu=true&with_head_pose=false&with_body_yaw=false&with_antenna_positions=false"


def _start_feeds(store: Store, host: str, stop: asyncio.Event) -> list[asyncio.Task[None]]:
    """Start the app-events, robot-state, fast IMU and daemon-log feeds as background tasks."""
    app_feed = read_websocket(
        f"ws://{host}:{APP_RPC_PORT}/rpc", store.add_rpc, partial(store.set_link, "app"), stop
    )
    robot_feed = read_websocket(
        f"ws://{host}:{DAEMON_PORT}/api/state/ws/full?{STATE_QUERY}",
        store.set_robot,
        partial(store.set_link, "robot"),
        stop,
    )
    imu_feed = read_websocket(
        f"ws://{host}:{DAEMON_PORT}/api/state/ws/full?{IMU_QUERY}", store.add_imu, partial(store.set_link, "imu"), stop
    )
    log_feed = read_text_websocket(
        f"ws://{host}:{DAEMON_PORT}/logs/ws/daemon", store.add_log_line, partial(store.set_link, "log"), stop
    )
    return [asyncio.create_task(feed) for feed in (app_feed, robot_feed, imu_feed, log_feed)]


def create_app(store: Store, robot_host: str | None) -> FastAPI:
    """Build the dashboard app.

    Args:
        store: Where feeds write and the page reads.
        robot_host: Robot address; None starts no feeds (used by tests).

    Returns:
        The FastAPI app.
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        stop = asyncio.Event()
        tasks = _start_feeds(store, robot_host, stop) if robot_host else []
        yield
        stop.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="Reachy Hub", lifespan=lifespan)

    @app.get("/api/snapshot")
    def snapshot() -> dict[str, Any]:
        return store.snapshot()

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    return app
