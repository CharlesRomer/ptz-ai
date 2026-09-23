"""Shared state for mock mode: failure toggles + a rotating fake tally.

The /debug page flips these flags so every red-tile path, checklist
auto-check and NO SIGNAL overlay can be demonstrated without hardware.
"""

from __future__ import annotations

import time

from ..config import Config

FLAGS = {
    "atem_down": "Disconnect ATEM",
    "camera_power_fail": "Kill Cam 2 PoE power",
    "obs_drop_frames": "OBS: drop frames",
    "stream_off": "OBS: stop streaming",
    "wifi_down": "WiFi extender offline",
    "controller_unplugged": "Unplug controller 2",
    "disk_full": "Recording disk almost full",
    "freeze_tally": "Freeze tally rotation",
}

ROTATE_SECONDS = 12


class MockScenario:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.flags: dict[str, bool] = {name: False for name in FLAGS}
        self._start = time.time()
        self.cam_inputs = [c.atem_input for c in config.cameras
                           if c.atem_input is not None] or [1, 2, 3, 4]
        self._frozen_step: int | None = None

    def toggle(self, flag: str) -> bool:
        if flag not in self.flags:
            raise KeyError(flag)
        self.flags[flag] = not self.flags[flag]
        if flag == "freeze_tally":
            self._frozen_step = self._step() if self.flags[flag] else None
        return self.flags[flag]

    def _step(self) -> int:
        if self._frozen_step is not None:
            return self._frozen_step
        return int((time.time() - self._start) / ROTATE_SECONDS)

    def program_input(self) -> int:
        return self.cam_inputs[self._step() % len(self.cam_inputs)]

    def preview_input(self) -> int:
        return self.cam_inputs[(self._step() + 1) % len(self.cam_inputs)]

    @property
    def dead_camera(self) -> "tuple[str | None, int | None]":
        """(camera_id, atem_input) affected by camera_power_fail."""
        if not self.flags["camera_power_fail"]:
            return None, None
        cams = [c for c in self.config.cameras if c.atem_input is not None]
        if len(cams) < 2:
            return None, None
        return cams[1].id, cams[1].atem_input

    @property
    def dead_port(self) -> int | None:
        """Switch port matching the dead camera (2nd expect_poe port)."""
        if not self.flags["camera_power_fail"]:
            return None
        poe_ports = [p for p in self.config.switch.ports if p.expect_poe]
        return poe_ports[1].port if len(poe_ports) >= 2 else None
