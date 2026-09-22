"""Mock pollers: same state shapes as the real ones, fake data.

Values drift plausibly so the dashboards look alive; the MockScenario
flags (from /debug) force every failure path.
"""

from __future__ import annotations

import random
import time

from ..config import Config
from ..pollers.base import BasePoller
from ..state import ERROR, OK, StateStore, WARN
from .scenario import MockScenario


class _Wander:
    """A value that drifts within [lo, hi]."""

    def __init__(self, lo: float, hi: float, step: float) -> None:
        self.lo, self.hi, self.step = lo, hi, step
        self.value = random.uniform(lo, hi)

    def next(self) -> float:
        self.value = max(self.lo, min(self.hi,
                         self.value + random.uniform(-self.step, self.step)))
        return self.value


class MockAtemPoller(BasePoller):
    section = "atem"

    def __init__(self, config: Config, store: StateStore, scenario: MockScenario):
        super().__init__(config, store, config.atem.poll_interval)
        self.scenario = scenario

    async def poll(self) -> None:
        sc = self.scenario
        if sc.flags["atem_down"]:
            self.store.update(self.section, {"connected": False}, status=ERROR,
                              message=f"ATEM at {self.config.atem.ip} not responding")
            return
        program, preview = sc.program_input(), sc.preview_input()
        tally = {str(n): {"program": n == program, "preview": n == preview}
                 for n in sc.cam_inputs}
        names = {str(c.atem_input): c.label for c in self.config.cameras
                 if c.atem_input is not None}
        self.store.update(self.section, {
            "connected": True,
            "model": "ATEM Mini Extreme ISO G2 (mock)",
            "program": program,
            "preview": preview,
            "tally": tally,
            "input_names": names,
            "streaming": None,
            "recording": True,
        }, status=OK, message="Connected")


class MockSwitchPoller(BasePoller):
    section = "switch"

    def __init__(self, config: Config, store: StateStore, scenario: MockScenario):
        super().__init__(config, store, config.switch.poll_interval)
        self.scenario = scenario
        self._watts = {p.port: _Wander(4.5, 7.5, 0.3)
                       for p in config.switch.ports if p.expect_poe}

    async def poll(self) -> None:
        dead_port = self.scenario.dead_port
        ports = []
        for p in self.config.switch.ports:
            if p.expect_poe:
                dead = p.port == dead_port
                watts = 0.0 if dead else round(self._watts[p.port].next(), 1)
                ports.append({
                    "port": p.port, "label": p.label, "expect_poe": True,
                    "link_up": not dead, "watts": watts,
                    "power_ok": not dead, "ok": not dead,
                    "detail": f"{watts} W, link up" if not dead else "no PoE power",
                })
            else:
                ports.append({
                    "port": p.port, "label": p.label, "expect_poe": False,
                    "link_up": True, "watts": None, "power_ok": None,
                    "ok": True, "detail": "link up",
                })
        bad = [p["label"] for p in ports if not p["ok"]]
        self.store.update(self.section, {"ports": ports, "ip": self.config.switch.ip},
                          status=ERROR if bad else OK,
                          message=("Problem: " + ", ".join(bad)) if bad else "All ports OK")


class MockObsPoller(BasePoller):
    section = "obs"

    def __init__(self, config: Config, store: StateStore, scenario: MockScenario):
        super().__init__(config, store, config.obs.poll_interval)
        self.scenario = scenario
        self._kbps = _Wander(5600, 6400, 150)
        self._cpu = _Wander(18, 38, 3)
        self._started = time.time()
        self._skipped = 0
        self._total = 0

    async def poll(self) -> None:
        sc = self.scenario
        active = not sc.flags["stream_off"]
        if not active:
            self._started = time.time()
        duration = int((time.time() - self._started) * 1000) if active else 0
        self._total += 60
        if sc.flags["obs_drop_frames"] and active:
            self._skipped += random.randint(3, 9)
        dropped_pct = round(100 * self._skipped / max(self._total, 1), 2)
        secs = duration // 1000
        timecode = f"{secs // 3600:02}:{secs % 3600 // 60:02}:{secs % 60:02}"

        status, message = OK, ("Streaming" if active else "OBS ready (not streaming)")
        if active and sc.flags["obs_drop_frames"]:
            status, message = WARN, f"Stream struggling: {dropped_pct}% frames dropped"

        self.store.update(self.section, {
            "connected": True,
            "stream": {
                "active": active, "reconnecting": False,
                "duration_ms": duration, "timecode": timecode,
                "kbps": round(self._kbps.next()) if active else 0,
                "dropped_pct": dropped_pct,
                "skipped_frames": self._skipped, "total_frames": self._total,
                "congestion": 0.4 if sc.flags["obs_drop_frames"] else 0.0,
            },
            "record": {"active": active, "timecode": timecode},
            "stats": {
                "cpu_pct": round(self._cpu.next(), 1),
                "mem_mb": 900, "fps": 30.0,
                "render_skip_pct": 0.1, "avg_render_ms": 4.2,
            },
        }, status=status, message=message)


class MockSysInfoPoller(BasePoller):
    section = "system"

    def __init__(self, config: Config, store: StateStore, scenario: MockScenario):
        super().__init__(config, store, config.system.poll_interval)
        self.scenario = scenario
        self._cpu = _Wander(8, 35, 4)
        self._boot = time.time() - 3600

    async def poll(self) -> None:
        cpu = round(self._cpu.next(), 1)
        disk_pct = 97.0 if self.scenario.flags["disk_full"] else 42.0
        uptime = int(time.time() - self._boot)
        status, message = OK, f"CPU {cpu:.0f}% · up {uptime // 3600}h {uptime % 3600 // 60}m"
        if disk_pct > self.config.system.disk_error_pct:
            status, message = ERROR, f"Disk almost full: {disk_pct:.0f}%"
        self.store.update(self.section, {
            "cpu_pct": cpu, "mem_pct": 55.0,
            "uptime_s": uptime, "uptime": f"{uptime // 3600}h {uptime % 3600 // 60}m",
            "disks": [{"path": d, "pct": disk_pct, "free_gb": round((100 - disk_pct) * 5, 1)}
                      for d in self.config.system.disks],
        }, status=status, message=message)


class MockPingPoller(BasePoller):
    section = "ping"

    def __init__(self, config: Config, store: StateStore, scenario: MockScenario):
        super().__init__(config, store, config.ping_interval)
        self.scenario = scenario

    async def poll(self) -> None:
        wifi_down = self.scenario.flags["wifi_down"]
        results = []
        for t in self.config.ping_targets:
            is_wifi = "wifi" in t.label.lower() or "extender" in t.label.lower()
            ok = not (wifi_down and is_wifi)
            results.append({"label": t.label, "ip": t.ip, "ok": ok,
                            "rtt_ms": round(random.uniform(0.5, 4.0), 1) if ok else None})
        down = [r["label"] for r in results if not r["ok"]]
        self.store.update(self.section, {"targets": results},
                          status=ERROR if down else OK,
                          message=("Unreachable: " + ", ".join(down)) if down
                          else "All network devices reachable")


class MockYoutubePoller(BasePoller):
    section = "youtube"

    def __init__(self, config: Config, store: StateStore, scenario: MockScenario):
        super().__init__(config, store, max(config.youtube.poll_interval, 5))
        self.scenario = scenario
        self.interval = 5  # snappier than real API polling, it's fake anyway

    async def poll(self) -> None:
        live = not self.scenario.flags["stream_off"]
        if live:
            self.store.update(self.section, {"live": True, "title": "Sunday Service (mock)",
                                             "video_id": "mock12345"},
                              status=OK, message="YouTube: LIVE confirmed")
        else:
            self.store.update(self.section, {"live": False}, status=WARN,
                              message="Not detected on YouTube (may be unlisted)")
