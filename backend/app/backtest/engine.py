"""Event-driven backtester.

Replays historical bars through a Strategy exactly the way the live engine
does, fills entries at the next bar's open (with slippage), honors stop
prices intrabar, and applies the same RiskManager rules used live.
"""
from __future__ import annotations

from typing import Optional

from ..config import RiskConfig
from ..models import Bar, Position, Signal, SignalType, TradeRecord
from ..risk.manager import RiskManager
from ..strategies.base import Strategy, StrategyContext
from .metrics import compute_metrics


class BacktestResult:
    def __init__(self, strategy: str, params: dict, trades: list[TradeRecord],
                 metrics: dict, signals: list[Signal]):
        self.strategy = strategy
        self.params = params
        self.trades = trades
        self.metrics = metrics
        self.signals = signals

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "params": self.params,
            "metrics": self.metrics,
            "trades": [t.model_dump() for t in self.trades],
            "signals": [s.model_dump() for s in self.signals],
        }


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        starting_equity: float = 5_000.0,
        risk_config: Optional[RiskConfig] = None,
        slippage: float = 0.01,
        use_stops: bool = True,
    ):
        self.strategy = strategy
        self.starting_equity = starting_equity
        self.risk = RiskManager(risk_config or RiskConfig(), starting_equity)
        self.slippage = slippage
        self.use_stops = use_stops

    def run(self, bars: list[Bar]) -> BacktestResult:
        ctx = StrategyContext(bars[0].symbol if bars else "?")
        equity = self.starting_equity
        trades: list[TradeRecord] = []
        all_signals: list[Signal] = []

        pending_entry: Optional[Signal] = None
        pending_exit: Optional[Signal] = None
        position: Optional[Position] = None
        entry_reason = ""
        entry_ts = 0.0
        stop_price: Optional[float] = None
        target_price: Optional[float] = None

        def close_position(price: float, ts: float, reason: str):
            nonlocal position, equity, stop_price, target_price
            assert position is not None
            pnl = round((price - position.avg_price) * position.qty, 2)
            trade = TradeRecord(
                symbol=position.symbol, entry_ts=entry_ts, exit_ts=ts,
                entry_price=position.avg_price, exit_price=round(price, 4),
                qty=position.qty, pnl=pnl,
                entry_reason=entry_reason, exit_reason=reason,
            )
            trades.append(trade)
            equity += pnl
            self.risk.record_trade(trade)
            position = None
            ctx.position = None
            stop_price = None
            target_price = None

        for bar in bars:
            # 1. Execute orders queued from the previous bar at this bar's open
            if pending_exit and position:
                close_position(bar.open - self.slippage, bar.ts, pending_exit.reason)
                pending_exit = None
            if pending_entry and position is None and not self.risk.halted:
                fill = bar.open + self.slippage
                qty, stop, target = self.risk.size_position(equity, fill, pending_entry.stop_price)
                qty = min(qty, int(equity / fill)) if fill > 0 else 0
                if qty > 0:
                    position = Position(symbol=bar.symbol, qty=qty, avg_price=round(fill, 4), last_price=fill)
                    ctx.position = position
                    entry_reason = pending_entry.reason
                    entry_ts = bar.ts
                    stop_price = stop
                    target_price = pending_entry.target_price or target
                pending_entry = None

            # 2. Intrabar stop / target while holding
            if position and self.use_stops:
                if stop_price is not None and bar.low <= stop_price:
                    close_position(stop_price, bar.ts, f"Stop hit at ${stop_price:.2f}")
                elif target_price is not None and bar.high >= target_price:
                    close_position(target_price, bar.ts, f"Target hit at ${target_price:.2f} (2:1 R/R)")

            # 3. Feed the strategy
            if position:
                position.last_price = bar.close
            signals = self.strategy.on_bar(ctx, bar)
            all_signals.extend(signals)
            for sig in signals:
                if sig.type == SignalType.ENTER_LONG and position is None:
                    pending_entry = sig
                elif sig.type in (SignalType.EXIT_LONG, SignalType.SCALE_OUT) and position is not None:
                    pending_exit = sig

        # Close any open position at the last bar
        if position and bars:
            close_position(bars[-1].close, bars[-1].ts, "End of data")

        metrics = compute_metrics(trades, self.starting_equity)
        metrics["ending_equity"] = round(self.starting_equity + sum(t.pnl for t in trades), 2)
        return BacktestResult(
            strategy=self.strategy.name,
            params=self.strategy.params,
            trades=trades,
            metrics=metrics,
            signals=all_signals,
        )
