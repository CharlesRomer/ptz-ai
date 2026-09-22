"""Reachability checks via the system `ping` binary.

Uses a subprocess instead of raw ICMP sockets because raw sockets need
Administrator rights on Windows; `ping.exe` needs nothing.
"""

from __future__ import annotations

import asyncio
import re
import sys

from ..state import ERROR, OK, WARN
from .base import BasePoller

_RTT_RE = re.compile(r"time[=<]\s*([\d.]+)\s*ms", re.IGNORECASE)


def ping_args(ip: str) -> list[str]:
    if sys.platform == "win32":
        return ["ping", "-n", "1", "-w", "1000", ip]
    if sys.platform == "darwin":
        return ["ping", "-c", "1", "-t", "2", ip]
    return ["ping", "-c", "1", "-W", "1", ip]  # linux


async def ping_once(ip: str) -> float | None:
    """Returns round-trip time in ms, or None if unreachable."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *ping_args(ip),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=4)
    except (OSError, asyncio.TimeoutError):
        return None
    if proc.returncode != 0:
        return None
    match = _RTT_RE.search(stdout.decode(errors="replace"))
    return float(match.group(1)) if match else 0.0


class PingPoller(BasePoller):
    section = "ping"

    def __init__(self, config, store):
        super().__init__(config, store, config.ping_interval)

    async def poll(self) -> None:
        targets = self.config.ping_targets
        rtts = await asyncio.gather(*(ping_once(t.ip) for t in targets))
        results = [
            {"label": t.label, "ip": t.ip, "ok": rtt is not None,
             "rtt_ms": round(rtt, 1) if rtt is not None else None}
            for t, rtt in zip(targets, rtts)
        ]
        down = [r["label"] for r in results if not r["ok"]]
        if not targets:
            status, message = WARN, "No ping targets configured"
        elif not down:
            status, message = OK, "All network devices reachable"
        elif len(down) == len(targets):
            status, message = ERROR, "Nothing reachable — check network"
        else:
            status, message = ERROR, f"Unreachable: {', '.join(down)}"
        self.store.update(self.section, {"targets": results},
                          status=status, message=message)
