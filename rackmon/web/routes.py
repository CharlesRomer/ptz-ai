"""HTTP + WebSocket routes. No auth anywhere by design: these pages run
on localhost kiosks; the server binds 127.0.0.1 by default."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response

STATIC_DIR = Path(__file__).parent / "static"

PAGES = {
    "/": "index.html",
    "/screen1": "screen1.html",
    "/screen2": "screen2.html",
    "/screen3": "screen3.html",
    "/debug": "debug.html",
}


def build_router(ctx) -> APIRouter:
    from ..app import build_snapshot  # late import to avoid a cycle

    router = APIRouter()

    for route, filename in PAGES.items():
        def _page(filename=filename) -> FileResponse:
            return FileResponse(STATIC_DIR / filename)
        router.get(route, include_in_schema=False)(_page)

    @router.get("/api/state")
    async def api_state() -> dict:
        return build_snapshot(ctx)

    @router.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        ctx.clients.add(ws)
        try:
            import json
            await ws.send_text(json.dumps(build_snapshot(ctx)))
            while True:
                await ws.receive_text()  # only listening for disconnect
        except WebSocketDisconnect:
            pass
        finally:
            ctx.clients.discard(ws)

    @router.get("/api/frame/{source_id}")
    async def api_frame(source_id: str) -> Response:
        entry = ctx.hub.get(source_id)
        if entry is None:
            raise HTTPException(404, f"no frames for '{source_id}'")
        jpeg, age = entry
        return Response(jpeg, media_type="image/jpeg", headers={
            "Cache-Control": "no-store",
            "X-Frame-Age": f"{age:.1f}",
        })

    @router.post("/api/checklist/{action}")
    async def api_checklist(action: str) -> dict:
        if action == "advance":
            ctx.engine.advance()
        elif action == "back":
            ctx.engine.back()
        elif action == "reset":
            ctx.engine.reset()
        else:
            raise HTTPException(404, f"unknown checklist action '{action}'")
        ctx.engine.tick()
        return ctx.store.get("checklist")

    @router.get("/api/debug/flags")
    async def api_debug_flags() -> dict:
        if ctx.scenario is None:
            raise HTTPException(404, "debug toggles only exist in mock mode")
        from ..mock.scenario import FLAGS
        return {"flags": ctx.scenario.flags, "labels": FLAGS}

    @router.post("/api/debug/toggle/{flag}")
    async def api_debug_toggle(flag: str) -> dict:
        if ctx.scenario is None:
            raise HTTPException(404, "debug toggles only exist in mock mode")
        try:
            value = ctx.scenario.toggle(flag)
        except KeyError:
            raise HTTPException(404, f"unknown flag '{flag}'") from None
        return {"flag": flag, "value": value}

    return router
