"""ATEM switcher status via rackmon's built-in protocol client.

(The PyATEMMax library was dropped: it connects to ATEM Mini Extreme ISO
G2 firmware but decodes nothing — see rackmon/atemproto.py, which speaks
just enough of the protocol to monitor tally, buses, names and
stream/record flags, and skips everything else by length.)

OBS remains the authoritative "are we streaming" source; ATEM
stream/record flags are shown when the switcher reports them.
"""

from __future__ import annotations

import asyncio

from ..config import Config
from ..state import ERROR, OK, WARN
from .base import BasePoller


class AtemPoller(BasePoller):
    section = "atem"

    def __init__(self, config: Config, store):
        super().__init__(config, store, config.atem.poll_interval)
        self.monitor = None
        self._task: asyncio.Task | None = None
        self.inputs = sorted({
            c.atem_input for c in config.cameras if c.atem_input is not None
        }) or [1, 2, 3, 4]

    async def setup(self) -> None:
        if not self.config.atem.ip:
            return
        from ..atemproto import AtemMonitor

        self.monitor = AtemMonitor(self.config.atem.ip)
        self._task = asyncio.create_task(self.monitor.run(), name="atem-proto")

    def _tally(self) -> dict[str, dict]:
        tally = {}
        for num in self.inputs:
            flags = self.monitor.tally_by_source.get(num)
            if flags is None:
                flags = self.monitor.tally_by_index.get(num, 0)
            tally[str(num)] = {"program": bool(flags & 1),
                               "preview": bool(flags & 2)}
        return tally

    async def poll(self) -> None:
        if not self.config.atem.ip:
            self.store.update(self.section, {"connected": False}, status=WARN,
                              message="No ATEM IP configured")
            return
        if self.monitor is None:
            await self.setup()

        if not self.monitor.connected:
            self.store.update(self.section, {"connected": False}, status=ERROR,
                              message=f"ATEM at {self.config.atem.ip} not responding")
            return

        names = {str(n): self.monitor.input_names.get(n, f"Input {n}")
                 for n in self.inputs}
        self.store.update(self.section, {
            "connected": True,
            "model": self.monitor.model or "ATEM",
            "program": self.monitor.program.get(0),
            "preview": self.monitor.preview.get(0),
            "tally": self._tally(),
            "input_names": names,
            "streaming": self.monitor.streaming,
            "recording": self.monitor.recording,
        }, status=OK, message=f"Connected · {self.monitor.model or 'ATEM'}")
