"""Streaming technical indicators.

Each indicator is incremental (O(1) per bar) so the same objects serve both the
live engine and the backtester without recomputation.
"""
from __future__ import annotations

from collections import deque
from typing import Optional


class EMA:
    def __init__(self, period: int):
        self.period = period
        self.multiplier = 2 / (period + 1)
        self.value: Optional[float] = None
        self._seed: list[float] = []

    def update(self, price: float) -> Optional[float]:
        if self.value is None:
            self._seed.append(price)
            if len(self._seed) >= self.period:
                self.value = sum(self._seed) / len(self._seed)
                self._seed = []
            return self.value
        self.value = (price - self.value) * self.multiplier + self.value
        return self.value


class SMA:
    def __init__(self, period: int):
        self.period = period
        self._window: deque[float] = deque(maxlen=period)
        self.value: Optional[float] = None

    def update(self, price: float) -> Optional[float]:
        self._window.append(price)
        if len(self._window) == self.period:
            self.value = sum(self._window) / self.period
        return self.value


class MACD:
    """MACD line, signal line, and histogram (default 12/26/9)."""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.fast_ema = EMA(fast)
        self.slow_ema = EMA(slow)
        self.signal_ema = EMA(signal)
        self.macd: Optional[float] = None
        self.signal: Optional[float] = None
        self.histogram: Optional[float] = None

    def update(self, price: float) -> tuple[Optional[float], Optional[float], Optional[float]]:
        fast = self.fast_ema.update(price)
        slow = self.slow_ema.update(price)
        if fast is not None and slow is not None:
            self.macd = fast - slow
            self.signal = self.signal_ema.update(self.macd)
            if self.signal is not None:
                self.histogram = self.macd - self.signal
        return self.macd, self.signal, self.histogram


class VWAP:
    """Session VWAP; call reset() at the start of each trading day."""

    def __init__(self):
        self._cum_pv = 0.0
        self._cum_vol = 0
        self.value: Optional[float] = None

    def reset(self):
        self._cum_pv = 0.0
        self._cum_vol = 0
        self.value = None

    def update(self, typical_price: float, volume: int) -> Optional[float]:
        self._cum_pv += typical_price * volume
        self._cum_vol += volume
        if self._cum_vol > 0:
            self.value = self._cum_pv / self._cum_vol
        return self.value


class Crossover:
    """Tracks the relationship between two series and reports crosses."""

    def __init__(self):
        self._prev_diff: Optional[float] = None

    def update(self, a: Optional[float], b: Optional[float]) -> Optional[str]:
        """Returns 'golden' (a crossed above b), 'death' (a crossed below b), or None."""
        if a is None or b is None:
            return None
        diff = a - b
        result = None
        if self._prev_diff is not None:
            if self._prev_diff <= 0 < diff:
                result = "golden"
            elif self._prev_diff >= 0 > diff:
                result = "death"
        self._prev_diff = diff
        return result
