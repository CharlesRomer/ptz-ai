"""ATEM switcher status via PyATEMMax.

PyATEMMax keeps its own receive thread and state cache; we connect once
and read the cached values on our poll interval. All reads are wrapped
defensively because attribute coverage varies with ATEM model/firmware —
anything unavailable becomes None ("unknown") instead of an error.

Note: streaming/recording status via PyATEMMax is not guaranteed on
newer firmware (ATEM Mini Extreme ISO G2). OBS is the authoritative
source for "are we streaming"; the ATEM tiles show what they can.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import Config
from ..state import ERROR, OK
from .base import BasePoller

log = logging.getLogger("rackmon.atem")


def _as_int(value: Any) -> int | None:
    """PyATEMMax wraps many values in ATEMConstant objects with .value."""
    if value is None:
        return None
    inner = getattr(value, "value", value)
    try:
        return int(inner)
    except (TypeError, ValueError):
        return None


class AtemPoller(BasePoller):
    section = "atem"

    def __init__(self, config: Config, store):
        super().__init__(config, store, config.atem.poll_interval)
        self.switcher = None
        self.inputs = sorted({
            c.atem_input for c in config.cameras if c.atem_input is not None
        }) or [1, 2, 3, 4]

    async def setup(self) -> None:
        if not self.config.atem.ip:
            return
        import PyATEMMax  # imported lazily so mock mode never needs it

        self.switcher = PyATEMMax.ATEMMax()
        try:
            self.switcher.setLogLevel(logging.CRITICAL)
        except Exception:  # noqa: BLE001 — logging setup is best-effort
            pass
        # Non-blocking; PyATEMMax keeps retrying/reconnecting on its own thread.
        self.switcher.connect(self.config.atem.ip)

    def _read_tally(self) -> dict[str, dict]:
        tally: dict[str, dict] = {}
        flags = self.switcher.tally.bySource.flags
        for num in self.inputs:
            entry = {"program": False, "preview": False}
            for key in (num, f"input{num}", str(num)):
                try:
                    f = flags[key]
                    entry = {"program": bool(f.program), "preview": bool(f.preview)}
                    break
                except Exception:  # noqa: BLE001 — key form varies by version
                    continue
            tally[str(num)] = entry
        return tally

    def _read_input_names(self) -> dict[str, str]:
        names = {}
        for num in self.inputs:
            try:
                names[str(num)] = str(self.switcher.inputProperties[num].longName)
            except Exception:  # noqa: BLE001
                names[str(num)] = f"Input {num}"
        return names

    def _read_optional_flag(self, *attr_paths: str) -> bool | None:
        """Probe attribute paths like 'streaming.streaming' across versions."""
        for path in attr_paths:
            obj: Any = self.switcher
            try:
                for part in path.split("."):
                    obj = getattr(obj, part)
                if obj is None:
                    continue
                return bool(obj)
            except Exception:  # noqa: BLE001
                continue
        return None

    async def poll(self) -> None:
        if not self.config.atem.ip:
            self.store.update(self.section, {"connected": False}, status="warn",
                              message="No ATEM IP configured")
            return
        if self.switcher is None:
            await self.setup()

        connected = bool(getattr(self.switcher, "connected", False))
        if not connected:
            self.store.update(self.section, {"connected": False}, status=ERROR,
                              message=f"ATEM at {self.config.atem.ip} not responding")
            return

        program = _as_int(self.switcher.programInput[0].videoSource)
        preview = _as_int(self.switcher.previewInput[0].videoSource)
        streaming = self._read_optional_flag(
            "streaming.streaming", "streamRTMP.streaming", "streaming.status")
        recording = self._read_optional_flag(
            "recording.recording", "recording.status", "recordingStatus.recording")

        self.store.update(self.section, {
            "connected": True,
            "model": str(getattr(self.switcher, "atemModel", "") or "ATEM"),
            "program": program,
            "preview": preview,
            "tally": self._read_tally(),
            "input_names": self._read_input_names(),
            "streaming": streaming,   # None = unknown on this firmware
            "recording": recording,
        }, status=OK, message="Connected")
