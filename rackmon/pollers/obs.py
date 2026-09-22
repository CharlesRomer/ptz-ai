"""OBS status via obs-websocket protocol v5 (simpleobsws).

GetStreamStatus/GetStats/GetRecordStatus every poll. Bitrate is derived
from the byte counter delta between polls. This poller also exposes
get_screenshot() used by the multiview for PGM/PVW tiles (the ATEM has
no IP video output, but OBS already ingests everything).
"""

from __future__ import annotations

import base64
import time

from ..config import Config
from ..state import ERROR, OK, WARN
from .base import BasePoller


class ObsPoller(BasePoller):
    section = "obs"

    def __init__(self, config: Config, store):
        super().__init__(config, store, config.obs.poll_interval)
        self.ws = None
        self._mod = None
        self._last_bytes: tuple[float, int] | None = None

    async def _ensure_connected(self) -> None:
        if self.ws is not None and getattr(self.ws, "identified", False):
            return
        if self._mod is None:
            import simpleobsws  # lazy so mock mode never needs it
            self._mod = simpleobsws
        if self.ws is not None:
            try:
                await self.ws.disconnect()
            except Exception:  # noqa: BLE001 — old socket may already be dead
                pass
        cfg = self.config.obs
        self.ws = self._mod.WebSocketClient(
            url=f"ws://{cfg.host}:{cfg.port}",
            password=cfg.password,
        )
        try:
            await self.ws.connect()
            await self.ws.wait_until_identified(timeout=5)
        except Exception as exc:
            self.ws = None
            raise RuntimeError(
                "OBS not reachable — is OBS running with the WebSocket "
                f"server enabled on port {cfg.port}? ({exc})"
            ) from exc
        if not getattr(self.ws, "identified", False):
            self.ws = None
            raise RuntimeError(
                "OBS refused the connection — check the WebSocket password "
                "(OBS → Tools → WebSocket Server Settings)")

    async def _call(self, request: str, data: dict | None = None) -> dict:
        req = self._mod.Request(request, data or None)
        resp = await self.ws.call(req)
        if not resp.ok():
            raise RuntimeError(f"OBS rejected {request}: {resp.requestStatus.comment}")
        return resp.responseData or {}

    async def poll(self) -> None:
        await self._ensure_connected()
        stream = await self._call("GetStreamStatus")
        stats = await self._call("GetStats")
        record = await self._call("GetRecordStatus")

        now = time.time()
        out_bytes = stream.get("outputBytes", 0)
        kbps = None
        if self._last_bytes is not None:
            t0, b0 = self._last_bytes
            if now > t0 and out_bytes >= b0:
                kbps = round((out_bytes - b0) * 8 / (now - t0) / 1000)
        self._last_bytes = (now, out_bytes)

        skipped = stream.get("outputSkippedFrames", 0)
        total = max(stream.get("outputTotalFrames", 0), 1)
        dropped_pct = round(100 * skipped / total, 2)
        congestion = stream.get("outputCongestion", 0.0)
        render_skipped = stats.get("renderSkippedFrames", 0)
        render_total = max(stats.get("renderTotalFrames", 0), 1)

        active = bool(stream.get("outputActive"))
        status, message = OK, ("Streaming" if active else "OBS ready (not streaming)")
        if active and (dropped_pct > 2 or congestion > 0.3):
            status = WARN
            message = f"Stream struggling: {dropped_pct}% frames dropped"

        self.store.update(self.section, {
            "connected": True,
            "stream": {
                "active": active,
                "reconnecting": bool(stream.get("outputReconnecting")),
                "duration_ms": stream.get("outputDuration", 0),
                "timecode": stream.get("outputTimecode", "00:00:00"),
                "kbps": kbps,
                "dropped_pct": dropped_pct,
                "skipped_frames": skipped,
                "total_frames": stream.get("outputTotalFrames", 0),
                "congestion": round(congestion, 3),
            },
            "record": {
                "active": bool(record.get("outputActive")),
                "timecode": record.get("outputTimecode", "00:00:00"),
            },
            "stats": {
                "cpu_pct": round(stats.get("cpuUsage", 0.0), 1),
                "mem_mb": round(stats.get("memoryUsage", 0.0)),
                "fps": round(stats.get("activeFps", 0.0), 1),
                "render_skip_pct": round(100 * render_skipped / render_total, 2),
                "avg_render_ms": round(stats.get("averageFrameRenderTime", 0.0), 2),
            },
        }, status=status, message=message)

    async def get_screenshot(self, source_name: str, width: int) -> bytes | None:
        """JPEG bytes of an OBS source/scene, or None if unavailable."""
        try:
            if self.ws is None or not getattr(self.ws, "identified", False):
                return None
            data = await self._call("GetSourceScreenshot", {
                "sourceName": source_name,
                "imageFormat": "jpg",
                "imageWidth": width,
                "imageCompressionQuality": 60,
            })
            image_data = data.get("imageData", "")
            _, _, b64 = image_data.partition("base64,")
            return base64.b64decode(b64) if b64 else None
        except Exception:  # noqa: BLE001 — screenshot failure just skips a frame
            return None
