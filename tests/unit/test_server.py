from fastapi.testclient import TestClient

from reachy_hub.server import create_app
from reachy_hub.store import Store


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
