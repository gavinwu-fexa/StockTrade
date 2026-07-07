"""WebSocket hub — fan-out of engine events to all connected UI clients."""
from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, type_: str, data: Any) -> None:
        if not self.connections:
            return
        msg = json.dumps({"type": type_, "data": data}, default=str)
        dead = []
        for ws in self.connections:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()
