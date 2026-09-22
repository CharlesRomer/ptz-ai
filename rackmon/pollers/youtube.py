"""Optional YouTube-side live confirmation via the Data API v3.

Runs only when api_key + channel_id are configured. Uses search with
eventType=live (100 quota units per call — default 90s interval stays
well inside the free 10k/day quota).

Caveat (documented in README): an API key can only see PUBLIC live
streams. Unlisted streams won't show up, so this tile is informational
(yellow at worst) and never turns red.
"""

from __future__ import annotations

import httpx

from ..config import Config
from ..state import OK, WARN
from .base import BasePoller

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


class YoutubePoller(BasePoller):
    section = "youtube"

    def __init__(self, config: Config, store):
        super().__init__(config, store, config.youtube.poll_interval)
        self._client: httpx.AsyncClient | None = None

    async def setup(self) -> None:
        self._client = httpx.AsyncClient(timeout=10)

    async def poll(self) -> None:
        cfg = self.config.youtube
        resp = await self._client.get(SEARCH_URL, params={
            "part": "snippet",
            "channelId": cfg.channel_id,
            "eventType": "live",
            "type": "video",
            "maxResults": 1,
            "key": cfg.api_key,
        })
        if resp.status_code != 200:
            reason = resp.json().get("error", {}).get("message", resp.text[:100]) \
                if resp.headers.get("content-type", "").startswith("application/json") \
                else resp.text[:100]
            self.store.update(self.section, {"live": None}, status=WARN,
                              message=f"YouTube API problem: {reason}")
            return
        items = resp.json().get("items", [])
        if items:
            snippet = items[0].get("snippet", {})
            self.store.update(self.section, {
                "live": True,
                "title": snippet.get("title"),
                "video_id": items[0].get("id", {}).get("videoId"),
            }, status=OK, message="YouTube: LIVE confirmed")
        else:
            self.store.update(self.section, {"live": False}, status=WARN,
                              message="Not detected on YouTube (may be unlisted)")

    def friendly_error(self, exc: Exception) -> str:
        return f"YouTube check failed: {exc}"
