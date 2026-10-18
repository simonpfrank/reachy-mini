"""Run the wake watcher: ``python -m reachy_wake`` (normally started by the sleep tool)."""

import logging
import sys

from reachy_wake.watcher import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(module)s %(funcName)s:%(lineno)d %(message)s",
)
sys.exit(run())
