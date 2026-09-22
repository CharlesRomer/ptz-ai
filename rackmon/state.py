"""In-memory state store shared by all pollers and the web layer.

Every device section carries status/message/updated_at so the frontend
maps status -> tile color with no per-device logic. A section that stops
updating (hung poller, dead thread) is downgraded to `warn` when its
snapshot is built, based on the poll interval it registered.
"""

from __future__ import annotations

import time
from typing import Any

OK = "ok"
WARN = "warn"
ERROR = "error"
UNKNOWN = "unknown"

STALE_FACTOR = 3.0  # section is stale after 3x its poll interval


def resolve_path(data: Any, dotted: str) -> Any:
    """Resolve 'obs.stream.active' or 'switch.ports.0.watts' against nested
    dicts/lists. Returns None if any hop is missing."""
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


class StateStore:
    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._intervals: dict[str, float] = {}
        self.version = 0

    def update(
        self,
        section: str,
        data: dict | None = None,
        *,
        status: str | None = None,
        message: str | None = None,
        interval: float | None = None,
    ) -> None:
        entry = dict(data or {})
        if status is not None:
            entry["status"] = status
        entry.setdefault("status", UNKNOWN)
        if message is not None:
            entry["message"] = message
        entry["updated_at"] = time.time()
        if interval is not None:
            self._intervals[section] = interval
        self._data[section] = entry
        self.version += 1

    def get(self, section: str) -> dict:
        return self._data.get(section, {})

    def snapshot(self) -> dict:
        now = time.time()
        out: dict[str, Any] = {}
        for key, val in self._data.items():
            entry = dict(val)
            interval = self._intervals.get(key)
            updated = entry.get("updated_at", now)
            if interval and now - updated > STALE_FACTOR * interval:
                # A hung-while-ok poller becomes a warn; a section already in
                # error keeps its real message (it's mid retry-backoff).
                if entry.get("status") == OK:
                    entry["status"] = WARN
                    entry["message"] = f"No update for {int(now - updated)}s"
                entry["stale"] = True
            out[key] = entry
        meta = dict(out.get("meta", {}))
        meta["version"] = self.version
        meta["now"] = now
        out["meta"] = meta
        return out
