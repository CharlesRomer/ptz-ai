"""Animated PIL test cards for mock-mode multiview tiles."""

from __future__ import annotations

import asyncio
import io
import time

from ..config import CameraConfig, Config, VideoConfig
from ..video.hub import FrameHub
from .scenario import MockScenario

PALETTE = [
    (30, 90, 160), (40, 130, 90), (150, 90, 40), (120, 50, 130),
    (60, 60, 120), (140, 60, 60), (50, 110, 110), (110, 110, 50),
]


class MockFrameSource:
    def __init__(self, cam: CameraConfig, video: VideoConfig, hub: FrameHub,
                 scenario: MockScenario, config: Config) -> None:
        self.cam = cam
        self.video = video
        self.hub = hub
        self.scenario = scenario
        self.config = config
        cams = [c.id for c in config.cameras]
        self.color = PALETTE[cams.index(cam.id) % len(PALETTE)]

    def _current_label_color(self) -> tuple[str, tuple[int, int, int]]:
        """PGM/PVW tiles mirror whichever camera is currently on air."""
        cid = self.cam.id.lower()
        if cid not in ("pgm", "pvw", "program", "preview"):
            return self.cam.label, self.color
        target = (self.scenario.program_input() if cid in ("pgm", "program")
                  else self.scenario.preview_input())
        for i, c in enumerate(self.config.cameras):
            if c.atem_input == target:
                return f"{self.cam.label}: {c.label}", PALETTE[i % len(PALETTE)]
        return self.cam.label, self.color

    def _render(self) -> bytes:
        from PIL import Image, ImageDraw

        width = self.video.jpeg_width
        height = int(width * 9 / 16)
        label, color = self._current_label_color()
        img = Image.new("RGB", (width, height), color)
        draw = ImageDraw.Draw(img)
        # bouncing box proves frames are updating
        t = time.time()
        x = int((t * 60) % (2 * (width - 40)))
        if x > width - 40:
            x = 2 * (width - 40) - x
        y = height - 50
        draw.rectangle([x, y, x + 30, y + 30], fill=(255, 255, 255))
        draw.text((12, 10), label, fill=(255, 255, 255))
        draw.text((12, 30), time.strftime("%H:%M:%S"), fill=(220, 220, 220))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()

    async def run(self) -> None:
        delay = 1.0 / max(self.cam.fps, 0.5)
        dead_input = None
        while True:
            _, dead_input = self.scenario.dead_camera
            if self.cam.atem_input is not None and self.cam.atem_input == dead_input:
                pass  # camera "unpowered": stop pushing frames -> NO SIGNAL overlay
            else:
                self.hub.set(self.cam.id, self._render())
            await asyncio.sleep(delay)
