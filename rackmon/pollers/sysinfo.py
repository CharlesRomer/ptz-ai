"""Local machine stats via psutil: CPU, memory, disks, uptime."""

from __future__ import annotations

import time

import psutil

from ..state import ERROR, OK, WARN
from .base import BasePoller


def _fmt_uptime(seconds: float) -> str:
    m, _ = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


class SysInfoPoller(BasePoller):
    section = "system"

    def __init__(self, config, store):
        super().__init__(config, store, config.system.poll_interval)

    async def poll(self) -> None:
        cfg = self.config.system
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        uptime = time.time() - psutil.boot_time()
        disks = []
        for path in cfg.disks:
            try:
                usage = psutil.disk_usage(path)
                disks.append({
                    "path": path,
                    "pct": round(usage.percent, 1),
                    "free_gb": round(usage.free / 1e9, 1),
                })
            except OSError as exc:
                disks.append({"path": path, "pct": None, "free_gb": None,
                              "error": str(exc)})

        status, message = OK, f"CPU {cpu:.0f}% · up {_fmt_uptime(uptime)}"
        worst = max((d["pct"] for d in disks if d["pct"] is not None), default=0)
        if any(d["pct"] is None for d in disks):
            status, message = WARN, "A configured disk could not be read"
        if cpu > cfg.cpu_warn_pct:
            status, message = WARN, f"CPU high: {cpu:.0f}%"
        if worst > cfg.disk_warn_pct:
            status, message = WARN, f"Disk {worst:.0f}% full"
        if worst > cfg.disk_error_pct:
            status, message = ERROR, f"Disk almost full: {worst:.0f}%"

        self.store.update(self.section, {
            "cpu_pct": round(cpu, 1),
            "mem_pct": round(mem, 1),
            "uptime_s": int(uptime),
            "uptime": _fmt_uptime(uptime),
            "disks": disks,
        }, status=status, message=message)
