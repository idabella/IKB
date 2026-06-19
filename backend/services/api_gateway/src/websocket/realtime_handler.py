"""
WebSocket placeholder for future realtime agent streaming.

The gateway currently proxies SSE from Knowledge Engine via HTTP.
This router exists so the gateway application can start without import errors.
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/ws", tags=["WebSocket"])


@router.websocket("/realtime")
async def realtime_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        await websocket.send_json(
            {
                "type": "info",
                "message": "WebSocket streaming is not implemented yet. Use GET /api/v1/agents/tasks/{id}/stream.",
            }
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return
