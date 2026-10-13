"""Run the dashboard: ``python -m reachy_hub``.

Environment:
    REACHY_HOST: robot address (default ``reachy-mini.local``).
    HUB_PORT: local port for the page (default 8710; 8000 and 8042 are taken on this Mac).
"""

import logging
import os

import uvicorn

from reachy_hub.server import create_app
from reachy_hub.store import Store


def main() -> None:
    """Start the hub on localhost and connect it to the robot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(module)s.%(funcName)s:%(lineno)d %(message)s",
    )
    host = os.environ.get("REACHY_HOST", "reachy-mini.local")
    port = int(os.environ.get("HUB_PORT", "8710"))
    uvicorn.run(create_app(Store(), robot_host=host), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
