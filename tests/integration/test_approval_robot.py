"""Site approval against the real conversation app's transcript history. No mocks.
Fails, saying what to start, when the conversation app is down."""

import json
import socket
from pathlib import Path

import pytest

from reachy_hub.utterances import record_typed
from robot_tools import approve_site, read_article


def _require_app() -> None:
    try:
        socket.create_connection(("127.0.0.1", 7860), timeout=2).close()
    except OSError:
        pytest.fail("conversation app not reachable at 127.0.0.1:7860; start it and rerun")


def test_app_history_gives_numbered_transcripts() -> None:
    _require_app()
    events = approve_site.history()
    assert all({"role", "text", "seq"} <= set(e) and e["role"] in {"user", "assistant"} for e in events)
    assert read_article.latest_seq() >= max((e["seq"] for e in events), default=0)


async def test_hub_records_typed_text_at_the_apps_current_position(tmp_path: Path) -> None:
    _require_app()
    log = tmp_path / "typed_messages.jsonl"
    assert await record_typed("ws://127.0.0.1:7860/rpc", "integration check", log) is True
    record = json.loads(log.read_text())
    assert record["text"] == "integration check" and record["after_seq"] <= read_article.latest_seq()


def test_model_cannot_approve_a_site_nobody_asked_about() -> None:
    _require_app()
    refused_at = read_article.latest_seq()
    status, reason = approve_site.verdict("never-asked-about.example", refused_at, approve_site.history())
    assert status == "refused" and "not asked" in reason
