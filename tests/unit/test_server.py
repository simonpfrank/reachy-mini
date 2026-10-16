from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from reachy_hub import server
from reachy_hub.server import create_app
from reachy_hub.store import Store
from reachy_hub.utterances import UtteranceError


def test_snapshot_endpoint_returns_store_contents() -> None:
    store = Store()
    store.set_robot({"control_mode": "enabled", "timestamp": "t"})
    with TestClient(create_app(store, robot_host=None)) as client:
        body = client.get("/api/snapshot").json()
    assert body["robot"]["motor_mode"] == "enabled"
    assert body["app_link"] == "not started"


def test_root_serves_dashboard_page() -> None:
    with TestClient(create_app(Store(), robot_host=None)) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "<title>Reachy Hub</title>" in response.text


def test_no_robot_host_means_no_feeds_started() -> None:
    store = Store()
    with TestClient(create_app(store, robot_host=None)):
        pass
    assert (store.app_link, store.robot_link) == ("not started", "not started")


def test_clear_endpoint_empties_the_event_list() -> None:
    store = Store()
    store.add_rpc({"jsonrpc": "2.0", "method": "conversation.turn", "params": {"state": "speaking"}})
    with TestClient(create_app(store, robot_host=None)) as client:
        assert len(client.get("/api/snapshot").json()["events"]) == 1
        assert client.post("/api/events/clear").json() == {"cleared": 1}
        assert client.get("/api/snapshot").json()["events"] == []


def test_typed_utterance_is_forwarded_and_visible_in_existing_logs(monkeypatch) -> None:
    sender = AsyncMock()
    monkeypatch.setattr(server, "send_utterance", sender)
    monkeypatch.setattr(server, "_start_feeds", lambda *args: [])
    with TestClient(create_app(Store(), robot_host="robot.local")) as client:
        response = client.post("/api/utterances", json={"text": "  Stop following my voice  "})
        events = client.get("/api/snapshot").json()["events"]
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    sender.assert_awaited_once_with("ws://robot.local:7860/rpc", "Stop following my voice")
    assert events[-1]["source"] == "hub"
    assert events[-1]["kind"] == "utterance.sent"
    assert events[-1]["data"]["text"] == "Stop following my voice"


@pytest.mark.parametrize("body", [{"text": ""}, {"text": "  "}, {}, {"text": None}])
def test_empty_or_invalid_utterance_never_reaches_robot(monkeypatch, body) -> None:
    sender = AsyncMock()
    monkeypatch.setattr(server, "send_utterance", sender)
    with TestClient(create_app(Store(), robot_host=None)) as client:
        response = client.post("/api/utterances", json=body)
    assert response.status_code == 422
    sender.assert_not_awaited()


def test_delivery_error_is_returned_and_recorded_in_telemetry(monkeypatch) -> None:
    monkeypatch.setattr(server, "send_utterance", AsyncMock(side_effect=UtteranceError("App unavailable", 503)))
    monkeypatch.setattr(server, "_start_feeds", lambda *args: [])
    with TestClient(create_app(Store(), robot_host="robot.local")) as client:
        response = client.post("/api/utterances", json={"text": "Hello"})
        events = client.get("/api/snapshot").json()["events"]
    assert response.status_code == 503
    assert response.json()["detail"] == "App unavailable"
    assert events[-1]["kind"] == "utterance.failed"
    assert events[-1]["data"] == {"text": "Hello", "error": "App unavailable"}


def test_unconfigured_robot_returns_clear_error() -> None:
    with TestClient(create_app(Store(), robot_host=None)) as client:
        response = client.post("/api/utterances", json={"text": "Hello"})
    assert response.status_code == 503
    assert response.json()["detail"] == "No robot is configured for this dashboard"
