"""FastAPI application entry point.

Run:  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .api.ws import manager
from .engine import create_engine, get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_engine()
    await engine.start()
    yield
    await engine.stop()


app = FastAPI(title="StockTrade", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # local personal app
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    eng = get_engine()
    # initial snapshot so the UI paints immediately
    await ws.send_text(json.dumps({"type": "mode", "data": {
        "mode": eng.mode.value,
        "read_only": eng.read_only,
        "port": getattr(eng.broker, "connected_port", None),
    }}, default=str))
    await ws.send_text(json.dumps({"type": "scanner", "data": eng.scanner_results()}, default=str))
    acct = eng.broker.account()
    await ws.send_text(json.dumps({"type": "account", "data": acct.model_dump()}, default=str))
    await ws.send_text(json.dumps({"type": "risk", "data": eng.risk.snapshot()}, default=str))
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "select":
                await eng.select_symbol(str(msg.get("symbol", "")).upper())
    except WebSocketDisconnect:
        manager.disconnect(ws)
