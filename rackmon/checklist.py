"""Guided startup checklist with declarative auto-checks.

Steps live in config/checklist.yaml. A step may declare an `auto_check`
that is evaluated against the live state snapshot every broadcast tick,
so the screen can show a live pass/fail chip next to the instruction.

The auto_check micro-DSL (no eval, safe to hand-edit):
    auto_check: {path: "obs.stream.active", equals: true}
    auto_check: {path: "system.cpu_pct", lte: 90}
    auto_check: {path: "switch.ports", all: {field: "power_ok", equals: true}}
Supported operators: equals, not_equals, gte, lte. With none given, the
value is checked for truthiness. `all` applies the inner check to every
item of a list (matching `field` on each item when given).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .state import StateStore, resolve_path


def _compare(value: Any, spec: dict) -> bool:
    if "equals" in spec:
        return value == spec["equals"]
    if "not_equals" in spec:
        return value != spec["not_equals"]
    if "gte" in spec:
        return value is not None and value >= spec["gte"]
    if "lte" in spec:
        return value is not None and value <= spec["lte"]
    return bool(value)


def check_condition(spec: dict, snapshot: dict) -> bool:
    """Evaluate one auto_check spec against a state snapshot."""
    if not isinstance(spec, dict) or "path" not in spec:
        return False
    value = resolve_path(snapshot, spec["path"])
    inner = spec.get("all")
    if inner is not None:
        items: list = []
        if isinstance(value, dict):
            items = list(value.values())
        elif isinstance(value, list):
            items = value
        if not items:
            return False
        field = inner.get("field")

        def item_value(item: Any) -> Any:
            if not field:
                return item
            return item.get(field) if isinstance(item, dict) else None

        return all(_compare(item_value(item), inner) for item in items)
    return _compare(value, spec)


def load_steps(path: Path) -> list[dict]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    steps = raw.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("checklist.yaml: 'steps' must be a list")
    for i, step in enumerate(steps):
        if not isinstance(step, dict) or "title" not in step:
            raise ValueError(f"checklist.yaml: step {i + 1} needs at least a 'title'")
        step.setdefault("id", f"step{i + 1}")
        step.setdefault("detail", "")
    return steps


DEFAULT_STEPS = [
    {"id": "power", "title": "Turn on the rack power strip",
     "detail": "Everything in the rack should light up."},
    {"id": "cams", "title": "Wait for cameras to power up",
     "detail": "This takes about a minute.",
     "auto_check": {"path": "switch.ports", "all": {"field": "ok", "equals": True}}},
    {"id": "atem", "title": "Confirm the ATEM tile is green on Screen 1",
     "auto_check": {"path": "atem.status", "equals": "ok"}},
    {"id": "obs", "title": "In OBS, click Start Streaming",
     "auto_check": {"path": "obs.stream.active", "equals": True}},
]


class ChecklistEngine:
    def __init__(self, steps: list[dict], store: StateStore) -> None:
        self.steps = steps
        self.store = store
        self.current = 0
        self.done: set[str] = set()

    def advance(self) -> None:
        if self.current < len(self.steps):
            self.done.add(self.steps[self.current]["id"])
            self.current = min(self.current + 1, len(self.steps))

    def back(self) -> None:
        if self.current > 0:
            self.current -= 1
            self.done.discard(self.steps[self.current]["id"])

    def reset(self) -> None:
        self.current = 0
        self.done.clear()

    def tick(self) -> None:
        """Re-evaluate auto-checks against current state and publish."""
        snapshot = self.store.snapshot()
        view = []
        for i, step in enumerate(self.steps):
            auto = step.get("auto_check")
            view.append({
                "id": step["id"],
                "title": step["title"],
                "detail": step.get("detail", ""),
                "auto": auto is not None,
                "auto_ok": check_condition(auto, snapshot) if auto else None,
                "done": step["id"] in self.done,
                "current": i == self.current,
            })
        self.store.update("checklist", {
            "steps": view,
            "current": self.current,
            "total": len(self.steps),
            "complete": self.current >= len(self.steps),
        }, status="ok")
