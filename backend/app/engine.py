"""Trading engine.

Wires together a DataFeed (SIM synthetic market or IBKR live) and a Broker
(paper simulator or IBKR), runs the scanner and the active strategy, routes
every order through the RiskManager, persists trades/fills to SQLite, and
broadcasts state to UI clients over the WebSocket hub.

Mode switching (SIM <-> PAPER) swaps the feed+broker pair at runtime; the
strategy, risk rules, and UI stay identical. LIVE mode deliberately has no
runtime path — it requires editing config.py.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from .api.ws import manager
from .brokers.base import Broker
from .brokers.paper import PaperBroker
from .config import Mode, settings
from .feeds.base import DataFeed
from .feeds.sim import SimFeed
from .models import (
    Bar,
    Fill,
    OrderRequest,
    OrderSide,
    Quote,
    Signal,
    SignalType,
    TradeRecord,
)
from .risk.manager import RiskManager
from .scanners import PICKER_REGISTRY
from .storage import get_storage
from .strategies import STRATEGY_REGISTRY
from .strategies.base import Strategy, StrategyContext

log = logging.getLogger(__name__)

SCANNER_INTERVAL = 2.0
ACCOUNT_INTERVAL = 1.0


class RoundTrips:
    """Builds completed TradeRecords from a raw fill stream (used for IBKR,
    where the broker doesn't report round trips itself)."""

    def __init__(self):
        self._open: dict[str, dict] = {}

    def add_fill(self, fill: Fill) -> Optional[TradeRecord]:
        pos = self._open.get(fill.symbol)
        if fill.side == OrderSide.BUY:
            if pos is None:
                self._open[fill.symbol] = {
                    "qty": fill.qty, "avg": fill.price,
                    "entry_ts": fill.ts, "realized": 0.0,
                }
            else:
                total = pos["avg"] * pos["qty"] + fill.price * fill.qty
                pos["qty"] += fill.qty
                pos["avg"] = total / pos["qty"]
            return None
        if pos is None:
            return None
        qty = min(fill.qty, pos["qty"])
        pos["realized"] += (fill.price - pos["avg"]) * qty
        pos["qty"] -= qty
        if pos["qty"] > 0:
            return None
        trade = TradeRecord(
            symbol=fill.symbol,
            entry_ts=pos["entry_ts"],
            exit_ts=fill.ts,
            entry_price=round(pos["avg"], 4),
            exit_price=fill.price,
            qty=qty,
            pnl=round(pos["realized"], 2),
        )
        del self._open[fill.symbol]
        return trade


class Engine:
    def __init__(self):
        self.storage = get_storage()
        self.mode: Mode = Mode.SIM
        self.feed: DataFeed = SimFeed()
        self.broker: Broker = PaperBroker(starting_cash=settings.starting_equity)
        self.risk = RiskManager(settings.risk, settings.starting_equity)
        self.contexts: dict[str, StrategyContext] = {}
        self.strategy: Strategy = STRATEGY_REGISTRY[settings.active_strategy]()
        self.auto_trade = False
        self.share_size = settings.default_share_size
        self.selected_symbol: Optional[str] = None
        self.signal_log: list[Signal] = []
        self.round_trips = RoundTrips()
        self.ibkr_error: Optional[str] = None
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._mode_lock = asyncio.Lock()

        self._wire_broker()
        self._wire_feed()
        self._restore_risk_day()

    # -- wiring ----------------------------------------------------------------

    def _wire_broker(self) -> None:
        self.broker.on_fill = self._on_fill
        if isinstance(self.broker, PaperBroker):
            self.broker.on_trade_closed = self._on_trade_closed

    def _wire_feed(self) -> None:
        self.feed.on_quote = self._on_quote
        self.feed.on_bar = self._on_bar

    def _restore_risk_day(self) -> None:
        """Rehydrate today's realized P&L and loser streak after a restart."""
        pnl, streak = self.storage.day_pnl(time.strftime("%Y-%m-%d"), self.mode.value)
        self.risk.day_realized_pnl = pnl
        self.risk.consecutive_losers = streak
        self.risk._check_halts()

    # -- lifecycle ---------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        await self.feed.start()
        symbols = [s.symbol for s in self.feed.snapshots()]
        if symbols and self.selected_symbol is None:
            self.selected_symbol = symbols[0]
        for sym in symbols:
            self._warm_context(sym)
        self._tasks = [
            asyncio.create_task(self._scanner_loop()),
            asyncio.create_task(self._account_loop()),
        ]

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        await self.feed.stop()
        await self.broker.disconnect()

    # -- mode switching -------------------------------------------------------------

    async def switch_mode(self, target: Mode, port: Optional[int] = None) -> None:
        """Swap feed+broker pairs. Raises ConnectionError if IBKR is unreachable.

        An explicit live port (e.g. Gateway 4001) is allowed for DATA ONLY:
        the broker comes up read-only and every order path refuses.
        """
        async with self._mode_lock:
            if target == self.mode and not port:
                return
            if target == Mode.LIVE:
                raise ValueError("LIVE mode must be enabled in config.py, deliberately.")

            if target == Mode.PAPER:
                from .brokers.ibkr import IBKRBroker
                from .feeds.ibkr import IbkrFeed

                broker = IBKRBroker(settings.ibkr, port=port)
                await broker.connect()          # raises ConnectionError w/ guidance
                feed = IbkrFeed(broker.ib)
            else:
                broker = PaperBroker(starting_cash=settings.starting_equity)
                feed = SimFeed()

            # tear down old pair
            for t in self._tasks:
                t.cancel()
            await self.feed.stop()
            await self.broker.disconnect()

            self.mode = target
            self.feed = feed
            self.broker = broker
            self.contexts = {}
            self.signal_log = []
            self.round_trips = RoundTrips()
            self.ibkr_error = None
            self.risk = RiskManager(settings.risk, settings.starting_equity)
            self._wire_broker()
            self._wire_feed()
            self._restore_risk_day()

            await self.feed.start()
            symbols = [s.symbol for s in self.feed.snapshots()]
            self.selected_symbol = symbols[0] if symbols else None
            if self.selected_symbol:
                await self.feed.watch(self.selected_symbol)
                self._warm_context(self.selected_symbol)
            self._tasks = [
                asyncio.create_task(self._scanner_loop()),
                asyncio.create_task(self._account_loop()),
            ]
            await manager.broadcast("mode", {
                "mode": self.mode.value,
                "read_only": self.read_only,
                "port": getattr(self.broker, "connected_port", None),
            })
            await manager.broadcast("selected", {"symbol": self.selected_symbol})

    @property
    def read_only(self) -> bool:
        return bool(getattr(self.broker, "read_only", False))

    # -- feed events -------------------------------------------------------------------

    async def _on_quote(self, quote: Quote) -> None:
        if isinstance(self.broker, PaperBroker):
            await self.broker.update_quote(quote)
        else:
            self.broker.update_last_price(quote.symbol, quote.last)  # type: ignore[attr-defined]
        if quote.symbol == self.selected_symbol:
            await manager.broadcast("quote", quote.model_dump())

    async def _on_bar(self, bar: Bar, completed: bool) -> None:
        if bar.symbol == self.selected_symbol:
            await manager.broadcast("bar" if completed else "bar_update", bar.model_dump())
        if not completed:
            return
        ctx = self.contexts.get(bar.symbol)
        if ctx is None:
            return
        ctx.position = next(
            (p for p in self.broker.positions() if p.symbol == bar.symbol), None
        )
        signals = self.strategy.on_bar(ctx, bar)
        for sig in signals:
            self.signal_log.append(sig)
            await manager.broadcast("signal", sig.model_dump())
            if self.auto_trade:
                await self.execute_signal(sig)

    # -- broker events --------------------------------------------------------------------

    async def _on_fill(self, fill: Fill) -> None:
        self.storage.record_fill(fill, self.mode.value)
        entry = {
            "kind": "fill", "ts": fill.ts, "symbol": fill.symbol,
            "side": fill.side.value, "qty": fill.qty, "price": fill.price,
        }
        await manager.broadcast("fill", entry)
        if not isinstance(self.broker, PaperBroker):
            trade = self.round_trips.add_fill(fill)
            if trade:
                await self._on_trade_closed(trade)
        await self._broadcast_account()

    async def _on_trade_closed(self, trade: TradeRecord) -> None:
        self.risk.record_trade(trade)
        self.storage.record_trade(trade, self.mode.value)
        await manager.broadcast("trade_closed", trade.model_dump())
        await manager.broadcast("risk", self.risk.snapshot())

    # -- loops -------------------------------------------------------------------------------

    async def _scanner_loop(self) -> None:
        while self._running:
            try:
                await manager.broadcast("scanner", self.scanner_results())
            except Exception as e:
                log.warning("scanner loop error: %s", e)
            await asyncio.sleep(SCANNER_INTERVAL)

    async def _account_loop(self) -> None:
        while self._running:
            try:
                await self._broadcast_account()
            except Exception as e:
                log.warning("account loop error: %s", e)
            await asyncio.sleep(ACCOUNT_INTERVAL)

    async def _broadcast_account(self) -> None:
        acct = self.broker.account()
        acct.day_realized_pnl = round(self.risk.day_realized_pnl, 2)
        acct.consecutive_losers = self.risk.consecutive_losers
        acct.trading_halted = self.risk.halted
        acct.halt_reason = self.risk.halt_reason
        await manager.broadcast("account", acct.model_dump())
        await manager.broadcast("positions", [
            {**p.model_dump(), "unrealized_pnl": round(p.unrealized_pnl, 2),
             "market_value": round(p.market_value, 2)}
            for p in self.broker.positions()
        ])

    # -- queries -----------------------------------------------------------------------------

    def scanner_results(self) -> list[dict]:
        picker = PICKER_REGISTRY[settings.active_picker]
        results = []
        for snap in self.feed.snapshots():
            res = picker.evaluate(snap)
            if res:
                results.append(res.model_dump())
        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    def bars(self, symbol: str) -> list[Bar]:
        return self.feed.history(symbol)

    def latest_quote(self, symbol: str) -> Optional[Quote]:
        if isinstance(self.broker, PaperBroker):
            return self.broker._quotes.get(symbol)
        for snap in self.feed.snapshots():
            if snap.symbol == symbol:
                return Quote(symbol=symbol, ts=time.time(), bid=snap.price,
                             ask=snap.price, last=snap.price)
        return None

    def _warm_context(self, symbol: str) -> None:
        if symbol in self.contexts:
            return
        ctx = StrategyContext(symbol)
        for bar in self.feed.history(symbol)[-200:]:
            self.strategy.on_bar(ctx, bar)
        self.contexts[symbol] = ctx

    # -- actions ------------------------------------------------------------------------------

    async def execute_signal(self, sig: Signal) -> Optional[dict]:
        if sig.type == SignalType.ENTER_LONG:
            return await self.place_order(OrderRequest(
                symbol=sig.symbol, side=OrderSide.BUY, qty=0,  # 0 → risk-sized
                source=sig.strategy,
            ), stop_price=sig.stop_price)
        pos = next((p for p in self.broker.positions() if p.symbol == sig.symbol), None)
        if pos:
            qty = pos.qty if sig.type == SignalType.EXIT_LONG else max(1, pos.qty // 2)
            return await self.place_order(OrderRequest(
                symbol=sig.symbol, side=OrderSide.SELL, qty=qty, source=sig.strategy,
            ))
        return None

    async def place_order(self, req: OrderRequest, stop_price: Optional[float] = None) -> dict:
        # Engine-level half of the read-only safeguard (broker enforces too).
        if self.read_only:
            reason = (
                "READ-ONLY: connected to a LIVE IBKR account — orders are "
                "disabled. Set up your paper account (Gateway port 4002 / "
                "TWS 7497) to trade."
            )
            await manager.broadcast("order_rejected", {
                "symbol": req.symbol, "side": req.side.value, "reason": reason,
            })
            return {"ok": False, "error": reason}
        quote = self.latest_quote(req.symbol)
        if quote is None:
            return {"ok": False, "error": f"No market data for {req.symbol}"}
        price = quote.ask if req.side == OrderSide.BUY else quote.bid

        decision = self.risk.approve(req, self.broker.account(), price, stop_price)
        if not decision.approved:
            await manager.broadcast("order_rejected", {
                "symbol": req.symbol, "side": req.side.value, "reason": decision.reason,
            })
            return {"ok": False, "error": decision.reason}

        req.qty = decision.qty
        order = await self.broker.submit(req)
        result = {
            "ok": order.status.value in ("filled", "submitted", "partial"),
            "order": order.model_dump(),
            "warnings": decision.warnings,
            "stop_price": decision.stop_price,
            "target_price": decision.target_price,
        }
        if order.reject_reason:
            result["error"] = order.reject_reason
        return result

    async def select_symbol(self, symbol: str) -> None:
        self.selected_symbol = symbol
        await self.feed.watch(symbol)
        self._warm_context(symbol)
        await manager.broadcast("selected", {"symbol": symbol})

    def set_strategy(self, name: str, params: Optional[dict] = None) -> None:
        cls = STRATEGY_REGISTRY[name]
        self.strategy = cls(params)
        settings.active_strategy = name
        # Re-warm contexts so indicator state matches the new strategy.
        old = list(self.contexts)
        self.contexts = {}
        for symbol in old:
            self._warm_context(symbol)


engine: Optional[Engine] = None


def get_engine() -> Engine:
    assert engine is not None, "engine not started"
    return engine


def create_engine() -> Engine:
    global engine
    engine = Engine()
    return engine
