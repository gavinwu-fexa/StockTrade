"""Interactive Brokers adapter via ib_insync.

Requires TWS or IB Gateway running with API connections enabled:
  - TWS paper: port 7497       - IB Gateway paper: port 4002
  - TWS live:  port 7496       - IB Gateway live:  port 4001

The broker owns the IB connection; IbkrFeed shares it. Imported lazily so
SIM mode runs without ib_insync/IBKR present.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Optional

from ..config import IBKRConfig
from ..models import (
    AccountState,
    Fill,
    Order,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from .base import Broker

log = logging.getLogger(__name__)


class IBKRBroker(Broker):
    def __init__(self, config: IBKRConfig, port: Optional[int] = None):
        super().__init__()
        self.config = config
        self.port = port                 # None → probe the paper ports
        self.connected_port: Optional[int] = None
        self.read_only = False           # forced True on live ports
        self.ib = None
        self._orders: dict[str, Order] = {}
        self._last_prices: dict[str, float] = {}
        self._summary: dict[str, str] = {}

    async def _try_connect(self, port: int, timeout: float) -> bool:
        from ib_insync import IB

        ib = IB()
        try:
            await asyncio.wait_for(
                ib.connectAsync(self.config.host, port, clientId=self.config.client_id),
                timeout=timeout,
            )
        except (asyncio.TimeoutError, OSError):
            with contextlib.suppress(Exception):
                ib.disconnect()
            return False
        self.ib = ib
        self.connected_port = port
        return True

    async def connect(self) -> None:
        # ib_insync binds to asyncio.get_event_loop(); make sure that's the
        # loop we're actually running on (uvicorn may use uvloop otherwise).
        asyncio.set_event_loop(asyncio.get_running_loop())

        candidates = [self.port] if self.port else list(self.config.paper_ports)
        for port in candidates:
            if await self._try_connect(port, timeout=6):
                break
        else:
            tried = ", ".join(str(p) for p in candidates)
            raise ConnectionError(
                f"Could not reach IBKR at {self.config.host} (tried port(s) {tried}). "
                "Is TWS / IB Gateway running with API connections enabled "
                "(Configure → API → Settings → 'Enable ActiveX and Socket Clients')?"
            )

        # Hard safeguard: a live-account connection is data-only. Orders are
        # refused here AND in the engine — there is no override switch.
        self.read_only = self.connected_port in self.config.live_ports
        self.ib.execDetailsEvent += self._on_exec_details
        # Snapshot the account summary once; afterwards account() reads
        # ib_insync's auto-updating accountValues() cache. (IB.accountSummary()
        # is NOT a cache read — it re-enters the event loop and deadlocks
        # when called from a running loop or a threadpool.)
        with contextlib.suppress(Exception):
            summary = await asyncio.wait_for(self.ib.accountSummaryAsync(), timeout=6)
            self._summary = {v.tag: v.value for v in summary}
        log.info(
            "connected to IBKR on port %s%s",
            self.connected_port,
            " (LIVE account — READ-ONLY, orders disabled)" if self.read_only else "",
        )

    async def disconnect(self) -> None:
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()
        self.ib = None

    @property
    def connected(self) -> bool:
        return self.ib is not None and self.ib.isConnected()

    def update_last_price(self, symbol: str, price: float) -> None:
        """Fed by the engine from live quotes to mark positions."""
        self._last_prices[symbol] = price

    def _contract(self, symbol: str):
        from ib_insync import Stock

        return Stock(symbol, "SMART", "USD")

    def _on_exec_details(self, trade, fill) -> None:
        if self.on_fill:
            f = Fill(
                order_id=str(trade.order.orderId),
                symbol=trade.contract.symbol,
                side=OrderSide.BUY if fill.execution.side == "BOT" else OrderSide.SELL,
                qty=int(fill.execution.shares),
                price=float(fill.execution.price),
                ts=time.time(),
            )
            asyncio.ensure_future(self.on_fill(f))

    async def submit(self, req: OrderRequest) -> Order:
        from ib_insync import LimitOrder, MarketOrder, StopOrder

        if self.read_only:
            return Order(
                id="rejected", request=req, status=OrderStatus.REJECTED,
                ts=time.time(),
                reject_reason=(
                    "READ-ONLY: connected to a LIVE account "
                    f"(port {self.connected_port}) — orders are disabled. "
                    "Connect to a paper port (7497/4002) to trade."
                ),
            )
        if not self.connected:
            return Order(
                id="rejected", request=req, status=OrderStatus.REJECTED,
                ts=time.time(), reject_reason="Not connected to IBKR",
            )
        action = "BUY" if req.side == OrderSide.BUY else "SELL"
        if req.type == OrderType.MARKET:
            ib_order = MarketOrder(action, req.qty)
        elif req.type == OrderType.LIMIT:
            ib_order = LimitOrder(action, req.qty, req.limit_price)
        else:
            ib_order = StopOrder(action, req.qty, req.stop_price)
        ib_order.outsideRth = True

        trade = self.ib.placeOrder(self._contract(req.symbol), ib_order)
        order = Order(
            id=str(trade.order.orderId),
            request=req,
            status=OrderStatus.SUBMITTED,
            ts=time.time(),
        )
        self._orders[order.id] = order
        return order

    async def cancel(self, order_id: str) -> bool:
        if self.read_only or not self.connected:
            return False
        for trade in self.ib.openTrades():
            if str(trade.order.orderId) == order_id:
                self.ib.cancelOrder(trade.order)
                return True
        return False

    async def cancel_all(self) -> int:
        if self.read_only or not self.connected:
            return 0
        trades = self.ib.openTrades()
        for trade in trades:
            self.ib.cancelOrder(trade.order)
        return len(trades)

    async def flatten(self, symbol: Optional[str] = None) -> list[Order]:
        if self.read_only:
            return []
        orders = []
        for pos in self.positions():
            if symbol and pos.symbol != symbol:
                continue
            if pos.qty > 0:
                orders.append(await self.submit(OrderRequest(
                    symbol=pos.symbol, side=OrderSide.SELL, qty=pos.qty, source="flatten",
                )))
        return orders

    def positions(self) -> list[Position]:
        if not self.connected:
            return []
        result = []
        for p in self.ib.positions():
            if p.position != 0:
                sym = p.contract.symbol
                # avgCost is per share for stocks
                avg = float(p.avgCost)
                result.append(Position(
                    symbol=sym,
                    qty=int(p.position),
                    avg_price=avg,
                    last_price=self._last_prices.get(sym, avg),
                ))
        return result

    def open_orders(self) -> list[Order]:
        if not self.connected:
            return []
        out = []
        for trade in self.ib.openTrades():
            oid = str(trade.order.orderId)
            if oid in self._orders:
                out.append(self._orders[oid])
        return out

    def account(self) -> AccountState:
        if not self.connected:
            return AccountState(equity=0, cash=0)
        values = dict(self._summary)
        # accountValues() is a pure cache read, auto-updated by ib_insync's
        # account subscription — safe to call from any context.
        with contextlib.suppress(Exception):
            for av in self.ib.accountValues():
                if av.tag in ("NetLiquidation", "TotalCashValue", "AvailableFunds"):
                    values[av.tag] = av.value
        equity = float(values.get("NetLiquidation", 0) or 0)
        cash = float(values.get("TotalCashValue", values.get("AvailableFunds", 0)) or 0)
        return AccountState(equity=equity, cash=cash)
