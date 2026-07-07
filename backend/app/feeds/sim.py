"""SIM feed: wraps the synthetic market (sim/market.py) in the DataFeed
interface. '1-min' bars close every SIM_BAR_SEC wall-clock seconds so
indicators develop at demo speed."""
from __future__ import annotations

import asyncio

from ..models import Bar, StockSnapshot
from ..sim.market import BarAggregator, build_universe, generate_history
from .base import DataFeed

SIM_BAR_SEC = 5
TICKS_PER_SEC = 4


class SimFeed(DataFeed):
    name = "sim"

    def __init__(self):
        super().__init__()
        self.universe = build_universe()
        self.aggregator = BarAggregator(timeframe_sec=SIM_BAR_SEC)
        self._history: dict[str, list[Bar]] = {
            s.symbol: generate_history(s, bars=90, timeframe_sec=SIM_BAR_SEC)
            for s in self.universe
        }
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    def snapshots(self) -> list[StockSnapshot]:
        return [s.snapshot() for s in self.universe]

    async def watch(self, symbol: str) -> None:
        pass  # everything already streams in SIM

    def history(self, symbol: str) -> list[Bar]:
        return list(self._history.get(symbol, []))

    async def _tick_loop(self) -> None:
        while self._running:
            for stock in self.universe:
                quote = stock.tick()
                completed = self.aggregator.add_quote(
                    quote, volume=max(1, stock.day_volume // 5000)
                )
                # completed bar first — consumers rely on ascending bar times
                if completed is not None:
                    self._history.setdefault(stock.symbol, []).append(completed)
                    if len(self._history[stock.symbol]) > 2000:
                        self._history[stock.symbol] = self._history[stock.symbol][-1000:]
                    if self.on_bar:
                        await self.on_bar(completed, True)
                if self.on_quote:
                    await self.on_quote(quote)
                current = self.aggregator.current_bar(stock.symbol)
                if current is not None and self.on_bar:
                    await self.on_bar(current, False)
            await asyncio.sleep(1 / TICKS_PER_SEC)
