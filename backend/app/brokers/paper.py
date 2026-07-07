"""Paper broker: instant simulated fills against the latest quote.

Market buys fill at the ask (+ slippage), sells at the bid (- slippage).
Limit orders rest until the market touches the limit price. Keeps its own
positions, cash, and realized P&L, and emits Fill events like a real broker.
"""
from __future__ import annotations

import itertools
import time
from typing import Optional

from ..models import (
    AccountState,
    Fill,
    Order,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Quote,
    TradeRecord,
)
from .base import Broker

_order_ids = itertools.count(1)


class PaperBroker(Broker):
    def __init__(self, starting_cash: float = 5_000.0, slippage: float = 0.01):
        super().__init__()
        self.cash = starting_cash
        self.starting_cash = starting_cash
        self.slippage = slippage
        self._positions: dict[str, Position] = {}
        self._quotes: dict[str, Quote] = {}
        self._open_orders: dict[str, Order] = {}
        self._completed_trades: list[TradeRecord] = []
        self._entry_meta: dict[str, tuple[float, str]] = {}  # symbol -> (entry_ts, reason)
        self.on_trade_closed = None  # Optional[Callable[[TradeRecord], Awaitable[None]]]

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    # -- market data feed (called by the sim/live data layer) ----------------

    async def update_quote(self, quote: Quote) -> None:
        self._quotes[quote.symbol] = quote
        pos = self._positions.get(quote.symbol)
        if pos:
            pos.last_price = quote.last
        await self._try_fill_resting_orders(quote)

    # -- order handling -------------------------------------------------------

    async def submit(self, req: OrderRequest) -> Order:
        order = Order(id=f"P{next(_order_ids)}", request=req, ts=time.time())
        quote = self._quotes.get(req.symbol)
        if quote is None:
            order.status = OrderStatus.REJECTED
            order.reject_reason = f"No market data for {req.symbol}"
            return order

        if req.type == OrderType.MARKET:
            price = self._fill_price(req.side, quote)
            await self._execute(order, price, quote.ts)
        else:
            order.status = OrderStatus.SUBMITTED
            self._open_orders[order.id] = order
            await self._try_fill_resting_orders(quote)
        return order

    def _fill_price(self, side: OrderSide, quote: Quote) -> float:
        if side == OrderSide.BUY:
            return round(quote.ask + self.slippage, 4)
        return round(max(quote.bid - self.slippage, 0.01), 4)

    async def _try_fill_resting_orders(self, quote: Quote) -> None:
        for order in list(self._open_orders.values()):
            req = order.request
            if req.symbol != quote.symbol or req.type != OrderType.LIMIT:
                continue
            assert req.limit_price is not None
            if req.side == OrderSide.BUY and quote.ask <= req.limit_price:
                del self._open_orders[order.id]
                await self._execute(order, min(req.limit_price, quote.ask), quote.ts)
            elif req.side == OrderSide.SELL and quote.bid >= req.limit_price:
                del self._open_orders[order.id]
                await self._execute(order, max(req.limit_price, quote.bid), quote.ts)

    async def _execute(self, order: Order, price: float, ts: float) -> None:
        req = order.request
        qty = req.qty

        if req.side == OrderSide.BUY:
            cost = qty * price
            if cost > self.cash:
                qty = int(self.cash / price) if price > 0 else 0
                if qty <= 0:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = "Insufficient cash"
                    return
            pos = self._positions.setdefault(req.symbol, Position(symbol=req.symbol))
            total_cost = pos.avg_price * pos.qty + price * qty
            pos.qty += qty
            pos.avg_price = total_cost / pos.qty
            pos.last_price = price
            self.cash -= qty * price
            if req.symbol not in self._entry_meta:
                self._entry_meta[req.symbol] = (ts, req.source)
        else:
            pos = self._positions.get(req.symbol)
            if pos is None or pos.qty <= 0:
                order.status = OrderStatus.REJECTED
                order.reject_reason = "No position to sell"
                return
            qty = min(qty, pos.qty)
            realized = (price - pos.avg_price) * qty
            pos.realized_pnl += realized
            pos.qty -= qty
            pos.last_price = price
            self.cash += qty * price
            if pos.qty == 0:
                entry_ts, entry_reason = self._entry_meta.pop(req.symbol, (ts, ""))
                trade = TradeRecord(
                    symbol=req.symbol,
                    entry_ts=entry_ts,
                    exit_ts=ts,
                    entry_price=pos.avg_price,
                    exit_price=price,
                    qty=qty,
                    pnl=round(pos.realized_pnl, 2),
                    entry_reason=entry_reason,
                    exit_reason=req.source,
                )
                self._completed_trades.append(trade)
                del self._positions[req.symbol]
                if self.on_trade_closed:
                    await self.on_trade_closed(trade)

        order.status = OrderStatus.FILLED
        order.filled_qty = qty
        order.avg_fill_price = price
        fill = Fill(order_id=order.id, symbol=req.symbol, side=req.side, qty=qty, price=price, ts=ts)
        if self.on_fill:
            await self.on_fill(fill)

    async def cancel(self, order_id: str) -> bool:
        order = self._open_orders.pop(order_id, None)
        if order:
            order.status = OrderStatus.CANCELLED
            return True
        return False

    async def cancel_all(self) -> int:
        n = len(self._open_orders)
        for order in self._open_orders.values():
            order.status = OrderStatus.CANCELLED
        self._open_orders.clear()
        return n

    async def flatten(self, symbol: Optional[str] = None) -> list[Order]:
        orders = []
        targets = [symbol] if symbol else list(self._positions.keys())
        for sym in targets:
            pos = self._positions.get(sym)
            if pos and pos.qty > 0:
                orders.append(await self.submit(OrderRequest(
                    symbol=sym, side=OrderSide.SELL, qty=pos.qty, source="flatten",
                )))
        return orders

    # -- state ---------------------------------------------------------------

    def positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.qty > 0]

    def open_orders(self) -> list[Order]:
        return list(self._open_orders.values())

    def trades(self) -> list[TradeRecord]:
        return list(self._completed_trades)

    def account(self) -> AccountState:
        unrealized = sum(p.unrealized_pnl for p in self._positions.values())
        market_value = sum(p.market_value for p in self._positions.values())
        realized = sum(t.pnl for t in self._completed_trades)
        return AccountState(
            equity=round(self.cash + market_value, 2),
            cash=round(self.cash, 2),
            day_realized_pnl=round(realized, 2),
            day_unrealized_pnl=round(unrealized, 2),
        )
