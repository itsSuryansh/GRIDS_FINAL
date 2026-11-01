"""WebSocket endpoint for live navigation streaming.

The socket is a pure subscriber: the simulation loop lives in the service, so
reconnecting (or opening several tabs) never creates duplicate loops.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.analytics_service import live_summary
from app.services.simulation_service import manager, simulation_service
from app.utils.logging import get_logger

router = APIRouter(tags=["realtime"])
log = get_logger("grids.ws")


@router.websocket("/ws/simulation")
async def simulation_socket(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        # greet with current state + a small backfill so a reconnect is seamless
        await ws.send_json({"type": "hello", "data": simulation_service.status()})
        run = simulation_service.run
        if run is not None and run.engine.frames:
            tail = run.engine.frames[-120:]
            await ws.send_json(
                {
                    "type": "backfill",
                    "data": [f.to_api() for f in tail],
                    "summary": live_summary(run.engine.frames),
                }
            )
        while True:
            # client messages are control pings only; commands go over REST so
            # there is a single source of truth for lifecycle transitions
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception as exc:  # pragma: no cover
        log.warning("websocket error: %s", exc)
        await manager.disconnect(ws)


@router.get("/ws/status")
def ws_status() -> dict:
    """Realtime channel diagnostics."""
    return {
        "connected_clients": manager.count,
        "running": (simulation_service.status() or {}).get("state") == "running",
    }
