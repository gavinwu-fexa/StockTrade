"""EMA crossover strategy with configurable fast/slow windows."""
from __future__ import annotations

from ..models import Bar, Signal, SignalType
from .base import Strategy, StrategyContext, register_strategy


@register_strategy
class EMACross(Strategy):
    name = "ema_cross"
    label = "EMA Crossover"
    description = (
        "Enter when the fast EMA crosses above the slow EMA; "
        "exit when it crosses back below. Windows are configurable."
    )
    default_params = {"fast": 9, "slow": 20, "stop_pct": 0.02}

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[Signal]:
        fast = ctx.ema(self.params["fast"]).update(bar.close)
        slow = ctx.ema(self.params["slow"]).update(bar.close)
        cross = ctx.crossover(f"ema{self.params['fast']}/{self.params['slow']}").update(fast, slow)

        if cross == "golden" and not ctx.in_position:
            stop = bar.close * (1 - self.params["stop_pct"])
            return [Signal(
                type=SignalType.ENTER_LONG,
                symbol=bar.symbol,
                ts=bar.ts,
                price=bar.close,
                stop_price=round(stop, 2),
                reason=f"EMA{self.params['fast']} crossed above EMA{self.params['slow']}",
                strategy=self.name,
            )]
        if cross == "death" and ctx.in_position:
            return [Signal(
                type=SignalType.EXIT_LONG,
                symbol=bar.symbol,
                ts=bar.ts,
                price=bar.close,
                reason=f"EMA{self.params['fast']} crossed below EMA{self.params['slow']}",
                strategy=self.name,
            )]
        return []
