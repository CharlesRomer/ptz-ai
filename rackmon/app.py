"""FastAPI app factory: wires config -> pollers -> state -> web.

If the config failed to load we still build an app whose every page
explains the problem, so the kiosk screens never sit blank.
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .checklist import DEFAULT_STEPS, ChecklistEngine, load_steps
from .config import Config
from .state import StateStore
from .video.hub import FrameHub, make_placeholder

log = logging.getLogger("rackmon")

STATIC_DIR = Path(__file__).parent / "web" / "static"
BROADCAST_INTERVAL = 0.5  # fast enough for the live controller-input bars


@dataclass
class AppContext:
    config: Config
    store: StateStore
    hub: FrameHub
    engine: ChecklistEngine
    scenario: Any = None  # MockScenario in mock mode
    clients: set = field(default_factory=set)
    obs_poller: Any = None


def make_pollers(ctx: AppContext) -> list:
    cfg = ctx.config
    if cfg.mock:
        from .mock.pollers import (MockAtemPoller, MockObsPoller, MockPingPoller,
                                   MockSwitchPoller, MockSysInfoPoller,
                                   MockYoutubePoller)
        sc = ctx.scenario
        return [
            MockAtemPoller(cfg, ctx.store, sc),
            MockSwitchPoller(cfg, ctx.store, sc),
            MockObsPoller(cfg, ctx.store, sc),
            MockSysInfoPoller(cfg, ctx.store, sc),
            MockPingPoller(cfg, ctx.store, sc),
            MockYoutubePoller(cfg, ctx.store, sc),
        ]

    from .pollers.atem import AtemPoller
    from .pollers.obs import ObsPoller
    from .pollers.pingcheck import PingPoller
    from .pollers.snmp_switch import SnmpSwitchPoller
    from .pollers.sysinfo import SysInfoPoller
    from .pollers.youtube import YoutubePoller

    pollers: list = [SysInfoPoller(cfg, ctx.store)]
    if cfg.ping_targets:
        pollers.append(PingPoller(cfg, ctx.store))
    if cfg.atem.ip:
        pollers.append(AtemPoller(cfg, ctx.store))
    if cfg.switch.ip:
        pollers.append(SnmpSwitchPoller(cfg, ctx.store))
    ctx.obs_poller = ObsPoller(cfg, ctx.store)
    pollers.append(ctx.obs_poller)
    if cfg.youtube.enabled:
        pollers.append(YoutubePoller(cfg, ctx.store))
    return pollers


def make_video_sources(ctx: AppContext) -> list:
    cfg = ctx.config
    sources = []
    if cfg.mock:
        from .mock.frames import MockFrameSource
        return [MockFrameSource(cam, cfg.video, ctx.hub, ctx.scenario, cfg)
                for cam in cfg.cameras]

    from .video.sources import FfmpegRtspSource, ObsScreenshotSource, SnapshotSource
    for cam in cfg.cameras:
        if cam.mode == "snapshot":
            sources.append(SnapshotSource(cam, cfg.video, ctx.hub))
        elif cam.mode == "rtsp":
            sources.append(FfmpegRtspSource(cam, cfg.video, ctx.hub))
        elif cam.mode == "obs" and ctx.obs_poller is not None:
            sources.append(ObsScreenshotSource(cam, cfg.video, ctx.hub, ctx.obs_poller))
        elif cam.mode == "mock":
            from .mock.frames import MockFrameSource
            from .mock.scenario import MockScenario
            sc = ctx.scenario or MockScenario(cfg)
            sources.append(MockFrameSource(cam, cfg.video, ctx.hub, sc, cfg))
    return sources


def build_snapshot(ctx: AppContext) -> dict:
    snap = ctx.store.snapshot()
    snap["frames"] = ctx.hub.ages()
    if ctx.scenario is not None:
        snap["debug_flags"] = ctx.scenario.flags
    return snap


async def broadcast_loop(ctx: AppContext) -> None:
    while True:
        await asyncio.sleep(BROADCAST_INTERVAL)
        try:
            ctx.engine.tick()
            text = json.dumps(build_snapshot(ctx))
        except Exception:  # noqa: BLE001 — a bad snapshot must not kill the loop
            log.exception("broadcast snapshot failed")
            continue
        for ws in list(ctx.clients):
            try:
                await ws.send_text(text)
            except Exception:  # noqa: BLE001 — client gone
                ctx.clients.discard(ws)


def _load_checklist_steps(cfg: Config) -> list[dict]:
    path = Path(cfg.checklist_file)
    if path.exists():
        try:
            return load_steps(path)
        except Exception as exc:  # noqa: BLE001
            log.warning("checklist file %s invalid (%s); using defaults", path, exc)
    return [dict(s) for s in DEFAULT_STEPS]


def create_app(config: Config | None, config_error: str | None = None) -> FastAPI:
    if config is None:
        return create_error_app(config_error or "Unknown configuration problem")

    store = StateStore()
    hub = FrameHub()
    scenario = None
    if config.mock:
        from .mock.scenario import MockScenario
        scenario = MockScenario(config)
    engine = ChecklistEngine(_load_checklist_steps(config), store)
    ctx = AppContext(config=config, store=store, hub=hub,
                     engine=engine, scenario=scenario)

    pollers = make_pollers(ctx)
    sources = make_video_sources(ctx)

    controller = None
    if config.control.enabled and config.control.controllers:
        if config.mock:
            from .gamepad import MockGamepadControl
            controller = MockGamepadControl(config, store, scenario)
        else:
            from .gamepad import GamepadControl
            controller = GamepadControl(config, store)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        store.update("meta", {
            "app": f"rackmon {__version__}",
            "mock": config.mock,
            "stale_after": config.video.stale_after,
            "cameras": [{"id": c.id, "label": c.label, "atem_input": c.atem_input}
                        for c in config.cameras],
        }, status="ok")
        for cam in config.cameras:
            hub.set(cam.id, make_placeholder(cam.label, config.video.jpeg_width))
        engine.tick()
        tasks = [asyncio.create_task(p.run(), name=f"poller:{p.section}")
                 for p in pollers]
        tasks += [asyncio.create_task(s.run(), name=f"video:{s.cam.id}")
                  for s in sources]
        if controller is not None:
            tasks.append(asyncio.create_task(controller.run(), name="gamepad"))
        tasks.append(asyncio.create_task(broadcast_loop(ctx), name="broadcast"))
        log.info("rackmon up: %d pollers, %d video sources, mock=%s",
                 len(pollers), len(sources), config.mock)
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="rackmon", version=__version__, lifespan=lifespan)
    app.state.ctx = ctx

    from .web.routes import build_router
    app.include_router(build_router(ctx))
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def create_error_app(message: str) -> FastAPI:
    """Every page explains the config problem instead of a blank kiosk."""
    app = FastAPI(title="rackmon (config error)")
    page = f"""<!doctype html><html><head><meta charset="utf-8">
    <title>rackmon — config problem</title>
    <meta http-equiv="refresh" content="10">
    <style>body{{background:#111;color:#eee;font-family:system-ui;padding:2em}}
    pre{{background:#2a1215;color:#ff8888;padding:1em;border-radius:8px;
         white-space:pre-wrap;font-size:1.1em}}</style></head>
    <body><h1>⚠️ rackmon cannot start</h1>
    <pre>{html.escape(message)}</pre>
    <p>Fix the config file and restart the RackMon service
    (or wait — this page retries every 10 seconds).</p></body></html>"""

    @app.get("/api/state")
    async def state() -> dict:
        return {"config_error": message}

    @app.get("/{_path:path}")
    async def any_page(_path: str) -> HTMLResponse:
        return HTMLResponse(page, status_code=200)

    return app
