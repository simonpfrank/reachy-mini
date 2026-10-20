"""Run the dashboard: ``python -m reachy_hub``.

Environment (also read from a ``.env`` file found from the current directory upwards;
real environment variables win over the file):
    REACHY_HOST: robot address (default ``reachy-mini.local``; ``127.0.0.1`` when run on the robot).
    HUB_HOST: address the page listens on (default ``127.0.0.1``, this machine only; ``0.0.0.0`` for the
        home network, as scripts/hub.sh does).
    HUB_PORT: port for the page (default 8710).
"""

import logging
import os

import uvicorn
from dotenv import find_dotenv, load_dotenv

from reachy_hub.server import create_app
from reachy_hub.store import Store


def main() -> None:
    """Start the hub and connect it to the robot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(module)s.%(funcName)s:%(lineno)d %(message)s",
    )
    load_dotenv(find_dotenv(usecwd=True))
    host = os.environ.get("REACHY_HOST", "reachy-mini.local")
    listen = os.environ.get("HUB_HOST", "127.0.0.1")
    port = int(os.environ.get("HUB_PORT", "8710"))
    uvicorn.run(create_app(Store(), robot_host=host), host=listen, port=port, log_level="warning")


if __name__ == "__main__":
    main()
