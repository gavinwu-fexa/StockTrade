"""Market data feed abstraction.

A feed produces three things for the engine:
  - Quote ticks           (on_quote)
  - Bars                  (on_bar with completed flag; in-progress bars update)
  - StockSnapshots        (snapshots() — scanner input for the pickers)

SimFeed synthesizes all three; IbkrFeed sources them from TWS/IB Gateway.
The engine is identical either way.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Optional

from ..models import Bar, Quote, StockSnapshot

QuoteHandler = Callable[[Quote], Awaitable[None]]
BarHandler = Callable[[Bar, bool], Awaitable[None]]  # (bar, completed)


class DataFeed(ABC):
    name: str = "base"

    def __init__(self):
        self.on_quote: Optional[QuoteHandler] = None
        self.on_bar: Optional[BarHandler] = None

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    def snapshots(self) -> list[StockSnapshot]:
        """Current view of the scan universe (for pickers)."""

    @abstractmethod
    async def watch(self, symbol: str) -> None:
        """Ensure quotes + bars stream for this symbol."""

    @abstractmethod
    def history(self, symbol: str) -> list[Bar]:
        """Warmup bars accumulated so far for the symbol."""
