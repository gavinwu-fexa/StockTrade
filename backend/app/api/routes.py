"""REST API. The frontend uses these for setup, orders, and backtests;
streaming data arrives over the WebSocket instead."""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..backtest.data import fetch_ibkr_history, generate_momentum_day
from ..backtest.engine import BacktestEngine
from ..config import Mode, settings
from ..engine import get_engine
from ..models import OrderRequest, OrderSide, OrderType
from ..scanners import PICKER_REGISTRY
from ..storage import get_storage
from ..strategies import STRATEGY_REGISTRY

router = APIRouter(prefix="/api")


# -- meta / state ------------------------------------------------------------

@router.get("/state")
def state():
    eng = get_engine()
    return {
        "mode": eng.mode.value,
        "read_only": eng.read_only,
        "ibkr_port": getattr(eng.broker, "connected_port", None),
        "market_condition": settings.market_condition,
        "starting_equity": settings.starting_equity,
        "share_size": eng.share_size,
        "auto_trade": eng.auto_trade,
        "selected_symbol": eng.selected_symbol,
        "active_picker": settings.active_picker,
        "active_strategy": settings.active_strategy,
        "strategy_params": eng.strategy.params,
        "risk": eng.risk.snapshot(),
        "pickers": [
            {"name": p.name, "label": p.label, "description": p.description}
            for p in PICKER_REGISTRY.values()
        ],
        "strategies": [
            {
                "name": cls.name,
                "label": cls.label,
                "description": cls.description,
                "default_params": cls.default_params,
            }
            for cls in STRATEGY_REGISTRY.values()
        ],
    }


class SettingsUpdate(BaseModel):
    share_size: Optional[int] = None
    auto_trade: Optional[bool] = None
    market_condition: Optional[str] = None
    active_picker: Optional[str] = None
    active_strategy: Optional[str] = None
    strategy_params: Optional[dict] = None


@router.post("/settings")
def update_settings(update: SettingsUpdate):
    eng = get_engine()
    if update.share_size is not None:
        eng.share_size = max(1, update.share_size)
    if update.auto_trade is not None:
        eng.auto_trade = update.auto_trade
    if update.market_condition in ("hot", "cold"):
        settings.market_condition = update.market_condition
    if update.active_picker:
        if update.active_picker not in PICKER_REGISTRY:
            raise HTTPException(404, f"Unknown picker {update.active_picker}")
        settings.active_picker = update.active_picker
    if update.active_strategy:
        if update.active_strategy not in STRATEGY_REGISTRY:
            raise HTTPException(404, f"Unknown strategy {update.active_strategy}")
        eng.set_strategy(update.active_strategy, update.strategy_params)
    elif update.strategy_params is not None:
        eng.set_strategy(settings.active_strategy, update.strategy_params)
    return state()


# -- market data ---------------------------------------------------------------

@router.get("/scanner")
def scanner():
    return get_engine().scanner_results()


@router.get("/bars/{symbol}")
def bars(symbol: str):
    return [b.model_dump() for b in get_engine().bars(symbol.upper())]


@router.post("/select/{symbol}")
async def select(symbol: str):
    eng = get_engine()
    await eng.select_symbol(symbol.upper())
    return {"selected": symbol.upper()}


# -- trading ---------------------------------------------------------------------

class PlaceOrder(BaseModel):
    symbol: str
    side: str                   # "buy" | "sell"
    qty: Optional[int] = None   # None → share size / risk-sized
    type: str = "market"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None


@router.post("/orders")
async def place_order(po: PlaceOrder):
    eng = get_engine()
    qty = po.qty if po.qty is not None else eng.share_size
    req = OrderRequest(
        symbol=po.symbol.upper(),
        side=OrderSide(po.side),
        qty=qty,
        type=OrderType(po.type),
        limit_price=po.limit_price,
        source="manual",
    )
    return await eng.place_order(req, stop_price=po.stop_price)


class FlattenBody(BaseModel):
    symbol: Optional[str] = None


@router.post("/flatten")
async def flatten(body: FlattenBody):
    eng = get_engine()
    orders = await eng.broker.flatten(body.symbol.upper() if body.symbol else None)
    return {"flattened": [o.model_dump() for o in orders]}


@router.post("/cancel_all")
async def cancel_all():
    n = await get_engine().broker.cancel_all()
    return {"cancelled": n}


@router.get("/positions")
def positions():
    return [
        {**p.model_dump(), "unrealized_pnl": round(p.unrealized_pnl, 2)}
        for p in get_engine().broker.positions()
    ]


@router.get("/account")
def account():
    return get_engine().broker.account().model_dump()


@router.get("/trades")
def trades(day: Optional[str] = None):
    return get_storage().trades(day=day)


@router.get("/history/daily")
def daily_history():
    return get_storage().daily_summary()


@router.post("/risk/rearm")
def rearm():
    get_engine().risk.rearm()
    return get_engine().risk.snapshot()


# -- mode switching -----------------------------------------------------------------

class ModeRequest(BaseModel):
    mode: str                      # "sim" | "paper"
    port: Optional[int] = None     # explicit IBKR port; live ports → read-only


@router.post("/mode")
async def switch_mode(body: ModeRequest):
    if body.mode not in (Mode.SIM.value, Mode.PAPER.value):
        raise HTTPException(400, f"Cannot switch to '{body.mode}' at runtime")
    eng = get_engine()
    try:
        await eng.switch_mode(Mode(body.mode), port=body.port)
    except ConnectionError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        raise HTTPException(500, f"Mode switch failed: {e}")
    return {
        "mode": eng.mode.value,
        "read_only": eng.read_only,
        "port": getattr(eng.broker, "connected_port", None),
        "selected": eng.selected_symbol,
    }


# -- backtesting -------------------------------------------------------------------

class BacktestRequest(BaseModel):
    strategy: str
    params: Optional[dict] = None
    data_source: str = "synthetic"     # "synthetic" | "ibkr"
    symbol: str = "SIM"
    days: int = 5
    starting_equity: Optional[float] = None
    seed: int = 1


@router.post("/backtest")
async def run_backtest(bt: BacktestRequest):
    if bt.strategy not in STRATEGY_REGISTRY:
        raise HTTPException(404, f"Unknown strategy {bt.strategy}")
    strategy = STRATEGY_REGISTRY[bt.strategy](bt.params)
    equity = bt.starting_equity or settings.starting_equity

    if bt.data_source == "ibkr":
        eng = get_engine()
        ib = getattr(eng.broker, "ib", None) if eng.mode == Mode.PAPER else None
        try:
            all_bars = await fetch_ibkr_history(
                bt.symbol.upper(), duration=f"{max(1, min(bt.days, 30))} D", ib=ib,
            )
        except (ConnectionError, OSError, asyncio.TimeoutError) as e:
            raise HTTPException(
                502,
                f"IBKR historical data unavailable: {e}. Start TWS/IB Gateway "
                "(or switch to PAPER mode first), or use synthetic data.",
            )
        except ValueError as e:
            raise HTTPException(404, str(e))
        if not all_bars:
            raise HTTPException(404, f"No historical bars returned for {bt.symbol}")
    else:
        all_bars = []
        for day in range(bt.days):
            all_bars.extend(generate_momentum_day(
                symbol=bt.symbol, seed=bt.seed + day, start_price=5.0, day_index=day,
            ))

    result = BacktestEngine(strategy, starting_equity=equity).run(all_bars)
    payload = result.to_dict()
    payload["data_source"] = bt.data_source
    payload["symbol"] = bt.symbol.upper()
    get_storage().record_backtest(
        bt.strategy, strategy.params, bt.data_source, bt.symbol.upper(),
        bt.days, result.metrics,
    )
    return payload


@router.get("/backtests")
def list_backtests():
    return get_storage().backtests()
