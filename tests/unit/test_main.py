"""Tests for reachy_hub.__main__: settings come from the environment or a .env file."""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import uvicorn

from reachy_hub import __main__ as hub_main


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, MagicMock]:
    """Run from an empty temp dir with a private environ and no real server start."""
    clean = {k: v for k, v in os.environ.items() if k not in ("REACHY_HOST", "HUB_PORT")}
    monkeypatch.setattr(os, "environ", clean)
    monkeypatch.chdir(tmp_path)
    create_app = MagicMock()
    run = MagicMock()
    monkeypatch.setattr(hub_main, "create_app", create_app)
    monkeypatch.setattr(uvicorn, "run", run)
    return {"create_app": create_app, "run": run}


def test_dotenv_file_sets_host_and_port(started: dict[str, MagicMock], tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("REACHY_HOST=10.0.0.9\nHUB_PORT=9001\n")
    hub_main.main()
    assert started["create_app"].call_args.kwargs["robot_host"] == "10.0.0.9"
    assert started["run"].call_args.kwargs["port"] == 9001


def test_real_env_var_beats_dotenv(started: dict[str, MagicMock], tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("REACHY_HOST=10.0.0.9\n")
    os.environ["REACHY_HOST"] = "192.168.1.50"
    hub_main.main()
    assert started["create_app"].call_args.kwargs["robot_host"] == "192.168.1.50"


def test_no_dotenv_uses_defaults(started: dict[str, MagicMock]) -> None:
    hub_main.main()
    assert started["create_app"].call_args.kwargs["robot_host"] == "reachy-mini.local"
    assert started["run"].call_args.kwargs["port"] == 8710
