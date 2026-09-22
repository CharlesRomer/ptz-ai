"""Poller lifecycle.

Every device integration subclasses BasePoller. The run loop owns all
error handling: a poller can never crash the process — any exception
turns its tile red with a friendly message and triggers exponential
backoff (capped at 30s) until the device answers again.
"""

from __future__ import annotations

import asyncio
import logging

from ..config import Config
from ..state import ERROR, StateStore

log = logging.getLogger("rackmon.poller")

MAX_BACKOFF = 30.0


class BasePoller:
    section: str = "unknown"

    def __init__(self, config: Config, store: StateStore, interval: float) -> None:
        self.config = config
        self.store = store
        self.interval = interval

    async def setup(self) -> None:  # override if needed; may raise
        pass

    async def poll(self) -> None:  # override; may raise
        raise NotImplementedError

    def friendly_error(self, exc: Exception) -> str:
        msg = str(exc) or type(exc).__name__
        return msg if len(msg) < 200 else msg[:200] + "…"

    async def run(self) -> None:
        self.store.update(self.section, {}, status="unknown",
                          message="Starting…", interval=self.interval)
        try:
            await self.setup()
        except Exception as exc:  # noqa: BLE001 — setup failure = red tile, keep trying
            log.warning("%s setup failed: %s", self.section, exc)
            self.store.update(self.section, {}, status=ERROR,
                              message=self.friendly_error(exc))
        failures = 0
        while True:
            try:
                await self.poll()
                failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — red tile, never crash
                failures += 1
                if failures <= 2:
                    log.warning("%s poll failed: %s", self.section, exc)
                self.store.update(self.section, {}, status=ERROR,
                                  message=self.friendly_error(exc))
            delay = self.interval
            if failures:
                delay = min(self.interval * (2 ** min(failures, 4)), MAX_BACKOFF)
            await asyncio.sleep(delay)
