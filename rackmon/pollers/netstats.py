"""Live network throughput via psutil: upload/download Mbps on the
busiest non-loopback interface."""

from __future__ import annotations

import time

import psutil

from ..state import OK
from .base import BasePoller

_LOOPBACK = {"lo", "lo0", "localhost"}


def _best_iface(counters: dict) -> str | None:
    best, best_bytes = None, 0
    for name, c in counters.items():
        if name.lower() in _LOOPBACK:
            continue
        total = c.bytes_sent + c.bytes_recv
        if total > best_bytes:
            best, best_bytes = name, total
    return best


class NetStatsPoller(BasePoller):
    section = "netstats"

    def __init__(self, config, store) -> None:
        super().__init__(config, store, 2.0)
        self._prev: dict | None = None
        self._prev_time: float | None = None

    async def poll(self) -> None:
        counters = psutil.net_io_counters(pernic=True)
        now = time.monotonic()
        iface = _best_iface(counters)

        if iface is None:
            self.store.update(self.section,
                              {"up_mbps": None, "down_mbps": None, "iface": None},
                              status="warn", message="No network interface found")
            self._prev, self._prev_time = counters, now
            return

        if self._prev is None or iface not in self._prev:
            self.store.update(self.section,
                              {"up_mbps": None, "down_mbps": None, "iface": iface},
                              status="ok", message="Measuring…")
            self._prev, self._prev_time = counters, now
            return

        dt = now - self._prev_time
        c, p = counters[iface], self._prev[iface]
        up_mbps = round((c.bytes_sent - p.bytes_sent) * 8 / dt / 1e6, 2)
        down_mbps = round((c.bytes_recv - p.bytes_recv) * 8 / dt / 1e6, 2)

        self.store.update(self.section, {
            "up_mbps": max(up_mbps, 0.0),
            "down_mbps": max(down_mbps, 0.0),
            "iface": iface,
        }, status=OK, message=f"↑ {max(up_mbps,0):.2f} Mbps  ↓ {max(down_mbps,0):.2f} Mbps")

        self._prev, self._prev_time = counters, now
