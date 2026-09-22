import time

from rackmon.state import StateStore, resolve_path


def test_update_and_snapshot():
    store = StateStore()
    store.update("obs", {"stream": {"active": True}}, status="ok", message="hi")
    snap = store.snapshot()
    assert snap["obs"]["status"] == "ok"
    assert snap["obs"]["stream"]["active"] is True
    assert snap["meta"]["version"] == 1


def test_status_defaults_to_unknown():
    store = StateStore()
    store.update("x", {"a": 1})
    assert store.snapshot()["x"]["status"] == "unknown"


def test_staleness_downgrades_ok_to_warn():
    store = StateStore()
    store.update("atem", {"connected": True}, status="ok", interval=0.01)
    time.sleep(0.05)  # > 3x interval
    snap = store.snapshot()
    assert snap["atem"]["status"] == "warn"
    assert snap["atem"]["stale"] is True


def test_staleness_keeps_error_status():
    store = StateStore()
    store.update("atem", {}, status="error", message="down", interval=0.01)
    time.sleep(0.05)
    assert store.snapshot()["atem"]["status"] == "error"


def test_fresh_section_not_stale():
    store = StateStore()
    store.update("atem", {}, status="ok", interval=60)
    assert "stale" not in store.snapshot()["atem"]


def test_resolve_path():
    data = {"a": {"b": [{"c": 5}]}}
    assert resolve_path(data, "a.b.0.c") == 5
    assert resolve_path(data, "a.b.9.c") is None
    assert resolve_path(data, "a.x") is None
    assert resolve_path(data, "a.b.zap") is None
