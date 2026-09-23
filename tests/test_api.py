import time

import pytest
from fastapi.testclient import TestClient

from rackmon.app import create_app
from rackmon.config import default_mock_config


@pytest.fixture()
def client():
    app = create_app(default_mock_config())
    with TestClient(app) as c:
        # let mock pollers publish their first cycle
        deadline = time.time() + 5
        while time.time() < deadline:
            snap = c.get("/api/state").json()
            if all(k in snap for k in ("atem", "obs", "switch", "system")):
                break
            time.sleep(0.1)
        yield c


def test_pages_serve(client):
    for path in ("/", "/screen1", "/screen2", "/screen3", "/debug"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


def test_state_shape(client):
    snap = client.get("/api/state").json()
    assert snap["meta"]["mock"] is True
    assert len(snap["meta"]["cameras"]) == 6
    assert snap["atem"]["status"] == "ok"
    assert snap["obs"]["stream"]["active"] is True
    assert all(p["ok"] for p in snap["switch"]["ports"])
    assert "frames" in snap


def test_frame_endpoint(client):
    resp = client.get("/api/frame/cam1")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content[:2] == b"\xff\xd8"
    assert client.get("/api/frame/nope").status_code == 404


def test_checklist_flow(client):
    ck = client.post("/api/checklist/advance").json()
    assert ck["current"] == 1
    ck = client.post("/api/checklist/back").json()
    assert ck["current"] == 0
    ck = client.post("/api/checklist/reset").json()
    assert ck["current"] == 0
    assert client.post("/api/checklist/bogus").status_code == 404


def test_debug_toggle_changes_state(client):
    flags = client.get("/api/debug/flags").json()["flags"]
    assert flags["atem_down"] is False
    assert client.post("/api/debug/toggle/atem_down").json()["value"] is True

    deadline = time.time() + 8
    status = None
    while time.time() < deadline:
        status = client.get("/api/state").json()["atem"]["status"]
        if status == "error":
            break
        time.sleep(0.2)
    assert status == "error"
    client.post("/api/debug/toggle/atem_down")
    assert client.post("/api/debug/toggle/bogus").status_code == 404


def test_websocket_pushes(client):
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert "meta" in first and "frames" in first
        second = ws.receive_json()  # broadcast loop push (~1s)
        assert second["meta"]["version"] >= first["meta"]["version"]


def test_config_error_app():
    app = create_app(None, config_error="switch.ip: not a valid IP")
    with TestClient(app) as c:
        assert c.get("/api/state").json()["config_error"].startswith("switch.ip")
        page = c.get("/screen1")
        assert page.status_code == 200
        assert "cannot start" in page.text


def test_kiosk_relaunch_windows_only(client):
    import sys
    if sys.platform != "win32":
        assert client.post("/api/kiosk/relaunch").status_code == 501
