"""Synthetic momentum-stock market for SIM mode.

Generates a small universe of low-float gappers that behave like the stocks
Ross Cameron trades: strong upward drift punctuated by micro pullbacks, plus
a few duds that don't meet the criteria (so the scanner has something to
filter out). Emits Quote ticks and aggregates them into 1-minute bars.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Optional

from ..models import Bar, Quote, StockSnapshot

HEADLINES = [
    "announces FDA fast-track designation for lead drug candidate",
    "reports Q2 revenue up 210% year-over-year",
    "wins $40M government contract",
    "announces partnership with major cloud provider",
    "receives buyout offer at significant premium",
    "announces positive Phase 2 trial results",
    "unveils AI product line at industry conference",
]


@dataclass
class SimStock:
    symbol: str
    prev_close: float
    float_shares: int
    avg_volume_30d: int
    has_news: bool
    headline: Optional[str]
    momentum: float            # drift per tick, decays & resurges
    target_gain: float = 0.6   # gains damp to ~0 as price nears this fraction over prev_close
    price: float = 0.0
    day_volume: int = 0
    spread: float = 0.02
    _phase: str = "surge"      # surge | pullback
    _phase_ticks: int = 0
    rng: random.Random = field(default_factory=random.Random)

    def tick(self) -> Quote:
        self._phase_ticks -= 1
        if self._phase_ticks <= 0:
            if self._phase == "surge":
                self._phase = "pullback"
                self._phase_ticks = self.rng.randint(4, 12)
            else:
                self._phase = "surge"
                self._phase_ticks = self.rng.randint(10, 40)

        # Damp upside as the day's gain approaches the stock's target so the
        # tape squeezes hard early then chops, instead of climbing forever.
        gain = self.price / self.prev_close - 1
        damp = max(0.05, 1 - max(0.0, gain) / max(self.target_gain, 0.05))
        drift = self.momentum * damp if self._phase == "surge" else -self.momentum * 0.55
        noise = self.rng.gauss(0, self.price * 0.0012)
        self.price = max(0.5, self.price * (1 + drift) + noise)

        base_vol = max(1, self.avg_volume_30d // 2000)
        mult = 3.0 if self._phase == "surge" else 1.2
        vol = int(base_vol * mult * self.rng.uniform(0.4, 1.8))
        self.day_volume += vol

        half = self.spread / 2
        return Quote(
            symbol=self.symbol,
            ts=time.time(),
            bid=round(self.price - half, 2),
            ask=round(self.price + half, 2),
            last=round(self.price, 2),
            bid_size=self.rng.randint(1, 50) * 100,
            ask_size=self.rng.randint(1, 50) * 100,
        )

    def snapshot(self) -> StockSnapshot:
        return StockSnapshot(
            symbol=self.symbol,
            price=round(self.price, 2),
            prev_close=self.prev_close,
            day_volume=self.day_volume,
            avg_volume_30d=self.avg_volume_30d,
            float_shares=self.float_shares,
            has_news=self.has_news,
            headline=self.headline,
            gap_pct=round((self.price - self.prev_close) / self.prev_close * 100, 2),
        )


class BarAggregator:
    """Aggregates quotes into fixed-interval bars."""

    def __init__(self, timeframe_sec: int = 60, timeframe_label: str = "1m"):
        self.timeframe_sec = timeframe_sec
        self.timeframe_label = timeframe_label
        self._current: dict[str, Bar] = {}

    def add_quote(self, q: Quote, volume: int) -> Optional[Bar]:
        """Returns the completed bar when a new interval starts, else None."""
        bucket = int(q.ts // self.timeframe_sec) * self.timeframe_sec
        bar = self._current.get(q.symbol)
        completed = None
        if bar is None or bar.ts != bucket:
            if bar is not None:
                completed = bar
            self._current[q.symbol] = Bar(
                symbol=q.symbol, ts=bucket,
                open=q.last, high=q.last, low=q.last, close=q.last,
                volume=volume, timeframe=self.timeframe_label,
            )
        else:
            bar.high = max(bar.high, q.last)
            bar.low = min(bar.low, q.last)
            bar.close = q.last
            bar.volume += volume
        return completed

    def current_bar(self, symbol: str) -> Optional[Bar]:
        return self._current.get(symbol)


def build_universe(seed: int = 42) -> list[SimStock]:
    rng = random.Random(seed)
    specs = [
        # A-quality candidates: low float, big gap, news
        ("HCTI", 4.10, 6_500_000, 380_000, True),
        ("MBIO", 6.80, 8_200_000, 510_000, True),
        ("SPRC", 2.45, 3_100_000, 290_000, True),
        ("GNS",  8.90, 12_500_000, 640_000, True),
        ("COSM", 1.85, 15_800_000, 720_000, False),   # B: no news
        # non-qualifiers to exercise the filter
        ("XELA", 0.72, 45_000_000, 4_200_000, False),  # too cheap, big float
        ("AAPL", 232.0, 15_000_000_000, 60_000_000, True),  # too expensive
        ("QNCX", 3.30, 18_000_000, 950_000, False),   # weak rel-vol / change
    ]
    stocks = []
    for sym, prev_close, flt, avg_vol, news in specs:
        gap = rng.uniform(0.12, 0.45) if news or rng.random() < 0.5 else rng.uniform(-0.02, 0.08)
        if sym in ("XELA", "QNCX"):
            gap = rng.uniform(0.01, 0.06)
        if sym == "AAPL":
            gap = rng.uniform(0.005, 0.02)
        stock = SimStock(
            symbol=sym,
            prev_close=prev_close,
            float_shares=flt,
            avg_volume_30d=avg_vol,
            has_news=news,
            headline=f"{sym} {rng.choice(HEADLINES)}" if news else None,
            momentum=rng.uniform(0.0006, 0.0022) if gap > 0.1 else rng.uniform(-0.0002, 0.0004),
            target_gain=rng.uniform(0.35, 1.5) if gap > 0.1 else rng.uniform(0.05, 0.15),
            rng=random.Random(rng.random()),
        )
        stock.price = prev_close * (1 + gap)
        # pre-load day volume so relative volume is meaningful at startup
        stock.day_volume = int(stock.avg_volume_30d * (rng.uniform(6, 25) if gap > 0.1 else rng.uniform(0.5, 3)))
        stocks.append(stock)
    return stocks


def generate_history(stock: SimStock, bars: int = 120, timeframe_sec: int = 60) -> list[Bar]:
    """Backfill plausible intraday history ending at the stock's current price."""
    rng = random.Random(stock.symbol)
    now = int(time.time() // timeframe_sec) * timeframe_sec
    # walk backwards from current price toward prev_close
    prices = [stock.price]
    for _ in range(bars):
        step = rng.gauss(0.0012, 0.004)
        prices.append(max(0.5, prices[-1] * (1 - step)))
    prices.reverse()

    out: list[Bar] = []
    for i in range(bars):
        ts = now - (bars - i) * timeframe_sec
        o, c = prices[i], prices[i + 1]
        hi = max(o, c) * (1 + abs(rng.gauss(0, 0.003)))
        lo = min(o, c) * (1 - abs(rng.gauss(0, 0.003)))
        vol = int(max(1, stock.avg_volume_30d / 390 * rng.uniform(2, 14)))
        out.append(Bar(
            symbol=stock.symbol, ts=ts,
            open=round(o, 2), high=round(hi, 2), low=round(lo, 2), close=round(c, 2),
            volume=vol, timeframe="1m",
        ))
    return out
