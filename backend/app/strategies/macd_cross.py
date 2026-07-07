"""MACD / signal-line crossover strategy.

Per the trading plan in the Small Account Tool Kit, "MACD crosses signal line"
is the primary trade invalidation — so the exit here fires on the bearish
cross regardless of how the entry happened.
"""
from __future__ import annotations

from ..models import Bar, Signal, SignalType
from .base import Strategy, StrategyContext, register_strategy


@register_strategy
class MACDCross(Strategy):
    name = "macd_cross"
    label = "MACD Signal Cross"
    description = (
        "Enter on MACD crossing above its signal line while above zero "
        "momentum; exit on the bearish cross (Ross's trade invalidation)."
    )
    default_params = {
        "fast": 12,
        "slow": 26,
        "signal": 9,
        "require_positive_macd": False,
        "stop_pct": 0.02,
    }

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[Signal]:
        macd = ctx.macd(self.params["fast"], self.params["slow"], self.params["signal"])
        macd_line, signal_line, _ = macd.update(bar.close)
        cross = ctx.crossover("macd/signal").update(macd_line, signal_line)

        if cross == "golden" and not ctx.in_position:
            if self.params["require_positive_macd"] and (macd_line or 0) <= 0:
                return []
            stop = bar.close * (1 - self.params["stop_pct"])
            return [Signal(
                type=SignalType.ENTER_LONG,
                symbol=bar.symbol,
                ts=bar.ts,
                price=bar.close,
                stop_price=round(stop, 2),
                reason="MACD crossed above signal line",
                strategy=self.name,
            )]
        if cross == "death" and ctx.in_position:
            return [Signal(
                type=SignalType.EXIT_LONG,
                symbol=bar.symbol,
                ts=bar.ts,
                price=bar.close,
                reason="MACD crossed below signal line (invalidation)",
                strategy=self.name,
            )]
        return []
