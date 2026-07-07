"""Strategy plugin interface.

A Strategy is a pure signal generator: it consumes bars and emits Signals.
It never talks to a broker — the RiskManager and execution engine decide
what to do with signals. This is what lets the same strategy code run in
backtests and live trading unchanged.

To add a strategy:

    @register_strategy
    class MyStrategy(Strategy):
        name = "my_strategy"
        label = "My Strategy"
        default_params = {"window": 10}
        def on_bar(self, ctx, bar): ...
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional, Type

from ..indicators import EMA, MACD, VWAP, Crossover, SMA
from ..models import Bar, Position, Signal


class StrategyContext:
    """Per-symbol state handed to a strategy on every bar.

    Owns indicator instances so strategies stay stateless across symbols;
    the engine keeps one context per (strategy, symbol) pair.
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.position: Optional[Position] = None
        self.bars: list[Bar] = []
        self._indicators: dict[str, object] = {}

    def _get(self, key: str, factory: Callable[[], object]):
        if key not in self._indicators:
            self._indicators[key] = factory()
        return self._indicators[key]

    def ema(self, period: int) -> EMA:
        return self._get(f"ema{period}", lambda: EMA(period))

    def sma(self, period: int) -> SMA:
        return self._get(f"sma{period}", lambda: SMA(period))

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> MACD:
        return self._get(f"macd{fast}-{slow}-{signal}", lambda: MACD(fast, slow, signal))

    def vwap(self) -> VWAP:
        return self._get("vwap", VWAP)

    def crossover(self, key: str) -> Crossover:
        return self._get(f"cross:{key}", Crossover)

    @property
    def in_position(self) -> bool:
        return self.position is not None and self.position.qty > 0


class Strategy(ABC):
    name: str = "base"
    label: str = "Base Strategy"
    description: str = ""
    default_params: dict = {}

    def __init__(self, params: Optional[dict] = None):
        self.params = {**self.default_params, **(params or {})}

    @abstractmethod
    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[Signal]:
        """Process one bar; return zero or more signals."""


STRATEGY_REGISTRY: dict[str, Type[Strategy]] = {}


def register_strategy(cls: Type[Strategy]) -> Type[Strategy]:
    STRATEGY_REGISTRY[cls.name] = cls
    return cls
