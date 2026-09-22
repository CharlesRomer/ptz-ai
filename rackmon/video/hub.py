"""FrameHub: latest JPEG per multiview source.

Every video mode (snapshot, rtsp/ffmpeg, obs screenshot, mock) lands
here, so there is exactly one serving path: GET /api/frame/{id}.
"""

from __future__ import annotations

import io
import time


class FrameHub:
    def __init__(self) -> None:
        self._frames: dict[str, tuple[bytes, float]] = {}

    def set(self, source_id: str, jpeg: bytes) -> None:
        self._frames[source_id] = (jpeg, time.time())

    def get(self, source_id: str) -> tuple[bytes, float] | None:
        """Returns (jpeg_bytes, age_seconds) or None."""
        entry = self._frames.get(source_id)
        if entry is None:
            return None
        jpeg, ts = entry
        return jpeg, time.time() - ts

    def ages(self) -> dict[str, float]:
        now = time.time()
        return {sid: round(now - ts, 1) for sid, (_, ts) in self._frames.items()}


def make_placeholder(label: str, width: int = 480) -> bytes:
    """Gray 'connecting…' card so /api/frame always has something to serve."""
    from PIL import Image, ImageDraw

    height = int(width * 9 / 16)
    img = Image.new("RGB", (width, height), (40, 44, 52))
    draw = ImageDraw.Draw(img)
    text = f"{label}\nconnecting…"
    draw.multiline_text((width / 2, height / 2), text, fill=(160, 160, 160),
                        anchor="mm", align="center")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()
