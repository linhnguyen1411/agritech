"""WebSocket router for real-time game events.

Channels
--------
- /ws/game/{user_id}   personal feed (balance updates, mission completions)
- /ws/market           public market feed (new listings, sales)
"""
import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.security import decode_token

router = APIRouter()


class ConnectionManager:
    """In-process WebSocket connection manager.

    For production scale-out, replace the per-process dict with a
    Redis pub/sub broadcaster shared across workers.
    """

    def __init__(self) -> None:
        self._personal: dict[str, list[WebSocket]] = {}
        self._market: list[WebSocket] = []

    # ── Personal channel ───────────────────────────────────────────────────

    async def connect_user(self, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._personal.setdefault(user_id, []).append(ws)

    def disconnect_user(self, user_id: str, ws: WebSocket) -> None:
        sockets = self._personal.get(user_id, [])
        if ws in sockets:
            sockets.remove(ws)

    async def send_to_user(self, user_id: str, event: str, data: object) -> None:
        for ws in list(self._personal.get(user_id, [])):
            try:
                await ws.send_text(json.dumps({"event": event, "data": data,
                                               "ts": datetime.now(UTC).isoformat()}))
            except Exception:
                self.disconnect_user(user_id, ws)

    # ── Market broadcast ───────────────────────────────────────────────────

    async def connect_market(self, ws: WebSocket) -> None:
        await ws.accept()
        self._market.append(ws)

    def disconnect_market(self, ws: WebSocket) -> None:
        if ws in self._market:
            self._market.remove(ws)

    async def broadcast_market(self, event: str, data: object) -> None:
        for ws in list(self._market):
            try:
                await ws.send_text(json.dumps({"event": event, "data": data,
                                               "ts": datetime.now(UTC).isoformat()}))
            except Exception:
                self.disconnect_market(ws)


manager = ConnectionManager()


@router.websocket("/game/{user_id}")
async def personal_ws(user_id: str, ws: WebSocket) -> None:
    """Personal feed – requires Bearer token in query param `token`."""
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = decode_token(token, expected_type="access")
        if payload.get("sub") != user_id:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect_user(user_id, ws)
    try:
        await ws.send_text(json.dumps({
            "event": "connected",
            "data": {"user_id": user_id},
            "ts": datetime.now(UTC).isoformat(),
        }))
        while True:
            # Keep-alive: echo any ping from client
            data = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
            if data == "ping":
                await ws.send_text(json.dumps({"event": "pong", "ts": datetime.now(UTC).isoformat()}))
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        manager.disconnect_user(user_id, ws)


@router.websocket("/market")
async def market_ws(ws: WebSocket) -> None:
    """Public market feed – no auth required (read-only)."""
    await manager.connect_market(ws)
    try:
        await ws.send_text(json.dumps({
            "event": "connected",
            "data": {"channel": "market"},
            "ts": datetime.now(UTC).isoformat(),
        }))
        while True:
            await asyncio.wait_for(ws.receive_text(), timeout=60.0)
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        manager.disconnect_market(ws)
