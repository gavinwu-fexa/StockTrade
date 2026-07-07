"""Domain models shared by scanners, strategies, brokers, and the API."""
from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Bar(BaseModel):
    symbol: str
    ts: float                 # epoch seconds (bar open time)
    open: float
    high: float
    low: float
    close: float
    volume: int
    timeframe: str = "1m"     # "1m" | "5m" | "1d"


class Quote(BaseModel):
    symbol: str
    ts: float
    bid: float
    ask: float
    last: float
    bid_size: int = 0
    ask_size: int = 0


class StockSnapshot(BaseModel):
    """Everything a StockPicker needs to evaluate one stock right now."""
    symbol: str
    price: float
    prev_close: float
    day_volume: int
    avg_volume_30d: int
    float_shares: Optional[int] = None
    has_news: bool = False
    headline: Optional[str] = None
    gap_pct: float = 0.0          # premarket gap vs previous close

    @property
    def change_pct(self) -> float:
        if self.prev_close <= 0:
            return 0.0
        return (self.price - self.prev_close) / self.prev_close * 100

    @property
    def relative_volume(self) -> float:
        if self.avg_volume_30d <= 0:
            return 0.0
        return self.day_volume / self.avg_volume_30d


class CriterionCheck(BaseModel):
    name: str
    passed: bool
    value: str                # human-readable, e.g. "7.2x" or "$6.45"
    detail: str = ""


class ScannerResult(BaseModel):
    symbol: str
    picker: str
    grade: str                # "A" | "B" | "C"
    score: float              # 0-100, for ranking
    price: float
    change_pct: float
    relative_volume: float
    float_shares: Optional[int]
    headline: Optional[str]
    checks: list[CriterionCheck]
    ts: float


class SignalType(str, Enum):
    ENTER_LONG = "enter_long"
    EXIT_LONG = "exit_long"
    SCALE_OUT = "scale_out"   # sell half


class Signal(BaseModel):
    type: SignalType
    symbol: str
    ts: float
    price: float              # reference price at signal time
    reason: str
    strategy: str
    stop_price: Optional[float] = None    # suggested stop for sizing
    target_price: Optional[float] = None


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    qty: int
    type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    source: str = "manual"    # "manual" | strategy name


class Order(BaseModel):
    id: str
    request: OrderRequest
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    ts: float = 0.0
    reject_reason: Optional[str] = None


class Fill(BaseModel):
    order_id: str
    symbol: str
    side: OrderSide
    qty: int
    price: float
    ts: float


class Position(BaseModel):
    symbol: str
    qty: int = 0
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    last_price: float = 0.0

    @property
    def unrealized_pnl(self) -> float:
        return (self.last_price - self.avg_price) * self.qty

    @property
    def market_value(self) -> float:
        return self.last_price * self.qty


class AccountState(BaseModel):
    equity: float
    cash: float
    day_realized_pnl: float = 0.0
    day_unrealized_pnl: float = 0.0
    consecutive_losers: int = 0
    trading_halted: bool = False
    halt_reason: Optional[str] = None


class TradeRecord(BaseModel):
    """A completed round trip, used by backtest metrics and the trade log."""
    symbol: str
    entry_ts: float
    exit_ts: float
    entry_price: float
    exit_price: float
    qty: int
    pnl: float
    entry_reason: str = ""
    exit_reason: str = ""
