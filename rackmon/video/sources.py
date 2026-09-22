"""Video frame producers for the tally multiview.

Each configured camera gets one source task that pushes JPEGs into the
FrameHub at its configured fps:

  snapshot — fetch the camera's HTTP snapshot URL
  rtsp     — persistent ffmpeg process decoding the RTSP substream to MJPEG
  obs      — obs-websocket GetSourceScreenshot (used for PGM/PVW)

Like pollers, a source can never crash the process; failures just mean
no fresh frame, which the UI shows as a NO SIGNAL overlay.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from ..config import CameraConfig, VideoConfig
from .hub import FrameHub

log = logging.getLogger("rackmon.video")

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"
RESTART_DELAY = 3.0


class VideoSource:
    def __init__(self, cam: CameraConfig, video: VideoConfig, hub: FrameHub) -> None:
        self.cam = cam
        self.video = video
        self.hub = hub

    async def run(self) -> None:
        raise NotImplementedError


class SnapshotSource(VideoSource):
    async def run(self) -> None:
        delay = 1.0 / max(self.cam.fps, 0.2)
        async with httpx.AsyncClient(timeout=5) as client:
            while True:
                try:
                    resp = await client.get(self.cam.snapshot_url)
                    if resp.status_code == 200 and resp.content[:2] == JPEG_SOI:
                        self.hub.set(self.cam.id, resp.content)
                except (httpx.HTTPError, OSError):
                    pass  # stale-frame overlay is the failure indicator
                await asyncio.sleep(delay)


class FfmpegRtspSource(VideoSource):
    def _command(self) -> list[str]:
        return [
            self.video.ffmpeg_path, "-nostdin", "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-i", self.cam.rtsp_url,
            "-vf", f"fps={self.cam.fps},scale={self.video.jpeg_width}:-2",
            "-q:v", "7",
            "-f", "mjpeg", "pipe:1",
        ]

    async def run(self) -> None:
        while True:
            try:
                await self._run_once()
            except FileNotFoundError:
                log.error("ffmpeg not found at '%s' — camera %s disabled. "
                          "Fix video.ffmpeg_path in config.yaml.",
                          self.video.ffmpeg_path, self.cam.id)
                return
            except (OSError, asyncio.IncompleteReadError):
                pass
            await asyncio.sleep(RESTART_DELAY)

    async def _run_once(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            *self._command(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        buf = b""
        try:
            while True:
                chunk = await proc.stdout.read(65536)
                if not chunk:
                    break
                buf += chunk
                # ffmpeg's mjpeg output is concatenated JPEGs; split on markers
                while True:
                    start = buf.find(JPEG_SOI)
                    if start < 0:
                        buf = b""
                        break
                    end = buf.find(JPEG_EOI, start + 2)
                    if end < 0:
                        buf = buf[start:]
                        break
                    self.hub.set(self.cam.id, buf[start:end + 2])
                    buf = buf[end + 2:]
        finally:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()


class ObsScreenshotSource(VideoSource):
    """Polls OBS for a source screenshot. Needs the shared ObsPoller,
    which owns the obs-websocket connection."""

    def __init__(self, cam, video, hub, obs_poller) -> None:
        super().__init__(cam, video, hub)
        self.obs_poller = obs_poller

    async def run(self) -> None:
        delay = 1.0 / max(self.cam.fps, 0.2)
        while True:
            jpeg = await self.obs_poller.get_screenshot(
                self.cam.obs_source, self.video.jpeg_width)
            if jpeg:
                self.hub.set(self.cam.id, jpeg)
            await asyncio.sleep(delay)
