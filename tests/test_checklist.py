import pytest

from rackmon.checklist import ChecklistEngine, check_condition, load_steps
from rackmon.state import StateStore

SNAP = {
    "obs": {"stream": {"active": True}, "status": "ok"},
    "system": {"cpu_pct": 42},
    "switch": {"ports": [{"ok": True, "watts": 6.1}, {"ok": True, "watts": 5.0}]},
    "atem": {"status": "error"},
}


@pytest.mark.parametrize("spec,expected", [
    ({"path": "obs.stream.active", "equals": True}, True),
    ({"path": "obs.stream.active", "equals": False}, False),
    ({"path": "atem.status", "equals": "ok"}, False),
    ({"path": "atem.status", "not_equals": "ok"}, True),
    ({"path": "system.cpu_pct", "lte": 90}, True),
    ({"path": "system.cpu_pct", "gte": 90}, False),
    ({"path": "system.cpu_pct"}, True),                       # truthy
    ({"path": "missing.path", "equals": 1}, False),
    ({"path": "switch.ports", "all": {"field": "ok", "equals": True}}, True),
    ({"path": "switch.ports", "all": {"field": "watts", "gte": 5.5}}, False),
    ({"path": "obs.stream", "all": {"field": "x", "equals": 1}}, False),  # dict vals
    ({"no_path": True}, False),
])
def test_check_condition(spec, expected):
    assert check_condition(spec, SNAP) is expected


def test_empty_list_fails_all():
    assert check_condition(
        {"path": "switch.ports", "all": {"field": "ok", "equals": True}},
        {"switch": {"ports": []}}) is False


def _engine(n=3):
    steps = [{"id": f"s{i}", "title": f"Step {i}", "detail": ""} for i in range(n)]
    steps[1]["auto_check"] = {"path": "obs.stream.active", "equals": True}
    store = StateStore()
    store.update("obs", {"stream": {"active": True}}, status="ok")
    return ChecklistEngine(steps, store), store


def test_advance_back_reset():
    engine, store = _engine()
    engine.tick()
    assert store.get("checklist")["current"] == 0
    engine.advance()
    engine.advance()
    engine.tick()
    ck = store.get("checklist")
    assert ck["current"] == 2
    assert ck["steps"][0]["done"] and ck["steps"][1]["done"]
    engine.back()
    engine.tick()
    ck = store.get("checklist")
    assert ck["current"] == 1 and not ck["steps"][1]["done"]
    engine.reset()
    engine.tick()
    assert store.get("checklist")["current"] == 0


def test_complete_flag():
    engine, store = _engine(2)
    engine.advance()
    engine.advance()
    engine.tick()
    assert store.get("checklist")["complete"] is True


def test_auto_ok_reflected():
    engine, store = _engine()
    engine.tick()
    steps = store.get("checklist")["steps"]
    assert steps[1]["auto"] is True and steps[1]["auto_ok"] is True
    assert steps[0]["auto"] is False and steps[0]["auto_ok"] is None


def test_load_steps_validation(tmp_path):
    good = tmp_path / "ok.yaml"
    good.write_text("steps:\n  - title: Hello\n", encoding="utf-8")
    steps = load_steps(good)
    assert steps[0]["id"] == "step1" and steps[0]["detail"] == ""

    bad = tmp_path / "bad.yaml"
    bad.write_text("steps:\n  - detail: no title\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_steps(bad)
