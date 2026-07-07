"""Micro-pullback — Ross Cameron's primary small-account setup.

The shape: a stock in a strong upward move prints one or a few small red
(or indecision) candles on declining volume — the micro pullback — then a
candle breaks back over the pullback high ("first candle to make a new
high"). Entry on that break, stop at the pullback low.

Invalidation (exit): MACD bearish cross or volume drying up, per the
trading plan worksheet.
"""
from __future__ import annotations

from ..models import Bar, Signal, SignalType
from .base import Strategy, StrategyContext, register_strategy


@register_strategy
class MicroPullback(Strategy):
    name = "micro_pullback"
    label = "Micro Pullback (Ross Cameron)"
    description = (
        "Buy the first candle to make a new high after a shallow 1-3 bar "
        "pullback within a strong up-move. Stop at pullback low; exit on "
        "MACD bearish cross or fading volume."
    )
    default_params = {
        "surge_bars": 4,          # lookback defining the up-move
        "surge_min_pct": 1.5,     # minimum % gain over that lookback
        "max_pullback_bars": 3,
        "max_pullback_pct": 3.0,  # pullback deeper than this = broken move
        "volume_fade_ratio": 0.4, # exit if volume < 40% of entry-leg average
    }

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[Signal]:
        ctx.bars.append(bar)
        macd_line, signal_line, _ = ctx.macd().update(bar.close)
        macd_cross = ctx.crossover("macd/signal").update(macd_line, signal_line)
        signals: list[Signal] = []
        bars = ctx.bars

        if ctx.in_position:
            if macd_cross == "death":
                return [self._exit(bar, "MACD crossed below signal line (invalidation)")]
            recent = bars[-8:]
            if len(recent) == 8:
                first_half = sum(b.volume for b in recent[:4]) / 4
                second_half = sum(b.volume for b in recent[4:]) / 4
                if first_half > 0 and second_half / first_half < self.params["volume_fade_ratio"]:
                    return [self._exit(bar, "Volume fading — momentum cooling off")]
            return []

        n = self.params["surge_bars"] + self.params["max_pullback_bars"] + 1
        if len(bars) < n:
            return signals

        window = bars[-n:]

        # Find the pullback: consecutive non-advancing bars immediately before
        # the current one.
        pullback: list[Bar] = []
        i = len(window) - 2
        while i >= 0 and window[i].close <= window[i].open and len(pullback) < self.params["max_pullback_bars"]:
            pullback.insert(0, window[i])
            i -= 1
        if not pullback:
            return signals

        surge = window[: i + 1]
        if len(surge) < 2:
            return signals

        surge_gain = (surge[-1].close - surge[0].open) / surge[0].open * 100
        if surge_gain < self.params["surge_min_pct"]:
            return signals

        pullback_high = max(b.high for b in pullback)
        pullback_low = min(b.low for b in pullback)
        surge_high = max(b.high for b in surge)
        depth_pct = (surge_high - pullback_low) / surge_high * 100
        if depth_pct > self.params["max_pullback_pct"]:
            return signals

        # Entry trigger: current bar takes out the pullback high.
        if bar.high > pullback_high and bar.close > bar.open:
            risk = bar.close - pullback_low
            signals.append(Signal(
                type=SignalType.ENTER_LONG,
                symbol=bar.symbol,
                ts=bar.ts,
                price=bar.close,
                stop_price=round(pullback_low, 2),
                target_price=round(bar.close + 2 * risk, 2),
                reason=(
                    f"Micro pullback: +{surge_gain:.1f}% surge, "
                    f"{len(pullback)}-bar dip, new high over ${pullback_high:.2f}"
                ),
                strategy=self.name,
            ))
        return signals

    def _exit(self, bar: Bar, reason: str) -> Signal:
        return Signal(
            type=SignalType.EXIT_LONG,
            symbol=bar.symbol,
            ts=bar.ts,
            price=bar.close,
            reason=reason,
            strategy=self.name,
        )
