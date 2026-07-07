"""IBKR market data feed via ib_insync (TWS / IB Gateway).

Scanner: polls IBKR's TOP_PERC_GAIN scan restricted to the $1-$20 band,
then enriches candidates with 30-day average volume (for relative volume)
and float from the fundamentals ReportSnapshot, both cached per day.

Bars: 1-min historical bars with keepUpToDate=True per watched symbol —
IBKR pushes updates to the in-progress bar and rolls new bars, which map
directly onto the engine's (bar, completed) contract.

Notes for paper accounts without market-data subscriptions: we request
delayed data (type 3) automatically, and news/catalyst detection is off,
so the best achievable scanner grade is B. Float parsing is best-effort.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import xml.etree.ElementTree as ET
from typing import Optional

from ..models import Bar, Quote, StockSnapshot
from .base import DataFeed

log = logging.getLogger(__name__)

SCAN_INTERVAL = 30.0
MAX_SCAN_ROWS = 12


class IbkrFeed(DataFeed):
    name = "ibkr"

    def __init__(self, ib):
        """ib: a connected ib_insync.IB instance (shared with IBKRBroker)."""
        super().__init__()
        self.ib = ib
        self._tickers: dict[str, object] = {}          # symbol -> Ticker (scan set + watched)
        self._contracts: dict[str, object] = {}        # symbol -> qualified Contract
        self._daily_stats: dict[str, dict] = {}        # symbol -> {avg_vol, prev_close, float, day}
        self._bars: dict[str, list[Bar]] = {}          # symbol -> accumulated 1-min bars
        self._live_bars: dict[str, object] = {}        # symbol -> BarDataList (keepUpToDate)
        self._watched: set[str] = set()
        self._scan_task: Optional[asyncio.Task] = None
        self._quote_task: Optional[asyncio.Task] = None
        self._running = False

    # -- lifecycle -------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        # Delayed data if no live subscription; harmless when live is available.
        self.ib.reqMarketDataType(3)
        self._scan_task = asyncio.create_task(self._scan_loop())
        self._quote_task = asyncio.create_task(self._quote_loop())

    async def stop(self) -> None:
        self._running = False
        for task in (self._scan_task, self._quote_task):
            if task:
                task.cancel()
        for bars in self._live_bars.values():
            with contextlib.suppress(Exception):
                self.ib.cancelHistoricalData(bars)
        for ticker in self._tickers.values():
            with contextlib.suppress(Exception):
                self.ib.cancelMktData(ticker.contract)
        self._live_bars.clear()
        self._tickers.clear()

    # -- scanning ----------------------------------------------------------------

    async def _scan_loop(self) -> None:
        from ib_insync import ScannerSubscription

        sub = ScannerSubscription(
            instrument="STK",
            locationCode="STK.US.MAJOR",
            scanCode="TOP_PERC_GAIN",
            abovePrice=1.0,
            belowPrice=20.0,
            aboveVolume=100_000,
            numberOfRows=MAX_SCAN_ROWS,
        )
        while self._running:
            try:
                rows = await self.ib.reqScannerDataAsync(sub)
                symbols = []
                for row in rows:
                    contract = row.contractDetails.contract
                    sym = contract.symbol
                    symbols.append(sym)
                    self._contracts[sym] = contract
                    if sym not in self._tickers:
                        self._tickers[sym] = self.ib.reqMktData(contract, "", False, False)
                    if sym not in self._daily_stats or self._daily_stats[sym]["day"] != _today():
                        await self._enrich(sym, contract)
                # drop streaming data for symbols that left the scan (keep watched)
                for sym in list(self._tickers):
                    if sym not in symbols and sym not in self._watched:
                        with contextlib.suppress(Exception):
                            self.ib.cancelMktData(self._tickers[sym].contract)
                        del self._tickers[sym]
            except Exception as e:
                log.warning("IBKR scan failed: %s", e)
            await asyncio.sleep(SCAN_INTERVAL)

    async def _enrich(self, symbol: str, contract) -> None:
        """Cache 30-day avg volume, previous close, and float (best effort)."""
        stats = {"avg_vol": 0, "prev_close": 0.0, "float": None, "day": _today()}
        try:
            # useRTH=False so the average is comparable to ticker.volume,
            # which counts pre/post-market consolidated volume.
            daily = await self.ib.reqHistoricalDataAsync(
                contract, endDateTime="", durationStr="30 D",
                barSizeSetting="1 day", whatToShow="TRADES", useRTH=False,
            )
            if daily:
                # exclude today's (partial, high-volume) bar from both stats
                prior = daily[:-1] if str(daily[-1].date) >= _today() else list(daily)
                if prior:
                    stats["avg_vol"] = int(sum(b.volume for b in prior) / len(prior))
                    stats["prev_close"] = float(prior[-1].close)
                else:
                    stats["prev_close"] = float(daily[-1].close)
        except Exception as e:
            log.info("daily history unavailable for %s: %s", symbol, e)
        try:
            xml_report = await asyncio.wait_for(
                self.ib.reqFundamentalDataAsync(contract, "ReportSnapshot"), timeout=10,
            )
            if xml_report:
                stats["float"] = _parse_float_shares(xml_report)
        except Exception:
            pass  # fundamentals frequently unavailable on paper accounts
        self._daily_stats[symbol] = stats

    def snapshots(self) -> list[StockSnapshot]:
        out = []
        for sym, ticker in self._tickers.items():
            stats = self._daily_stats.get(sym)
            if not stats:
                continue
            price = _ticker_price(ticker)
            if price is None or price <= 0:
                continue
            day_volume = int(v) if _num(v := ticker.volume) else 0
            # ticker.close is the prior session's close — the most reliable
            # source for percent-change; daily-bar stats are the fallback.
            prev_close = float(ticker.close) if _num(ticker.close) else (stats["prev_close"] or price)
            out.append(StockSnapshot(
                symbol=sym,
                price=price,
                prev_close=prev_close,
                day_volume=day_volume,
                avg_volume_30d=stats["avg_vol"],
                float_shares=stats["float"],
                has_news=False,       # needs an IBKR news subscription
                headline=None,
            ))
        return out

    # -- quotes ---------------------------------------------------------------------

    async def _quote_loop(self) -> None:
        """Forward pending ticker updates as Quote events (~4 Hz)."""
        while self._running:
            for sym, ticker in list(self._tickers.items()):
                price = _ticker_price(ticker)
                if price is None:
                    continue
                if self.on_quote:
                    await self.on_quote(Quote(
                        symbol=sym,
                        ts=time.time(),
                        bid=float(ticker.bid) if _num(ticker.bid) else price,
                        ask=float(ticker.ask) if _num(ticker.ask) else price,
                        last=price,
                        bid_size=int(ticker.bidSize or 0),
                        ask_size=int(ticker.askSize or 0),
                    ))
            await asyncio.sleep(0.25)

    # -- bars -----------------------------------------------------------------------

    async def watch(self, symbol: str) -> None:
        if symbol in self._watched:
            return
        self._watched.add(symbol)
        contract = self._contracts.get(symbol)
        if contract is None:
            from ib_insync import Stock
            contract = Stock(symbol, "SMART", "USD")
            qualified = await self.ib.qualifyContractsAsync(contract)
            if not qualified:
                log.warning("cannot qualify %s", symbol)
                return
            contract = qualified[0]
            self._contracts[symbol] = contract
        if symbol not in self._tickers:
            self._tickers[symbol] = self.ib.reqMktData(contract, "", False, False)

        bars = await self.ib.reqHistoricalDataAsync(
            contract, endDateTime="", durationStr="1 D",
            barSizeSetting="1 min", whatToShow="TRADES", useRTH=False,
            keepUpToDate=True,
        )
        self._live_bars[symbol] = bars
        self._bars[symbol] = [_to_bar(symbol, b) for b in bars[:-1]]

        def on_update(barlist, has_new_bar):
            if not self._running:
                return
            if has_new_bar and len(barlist) >= 2:
                completed = _to_bar(symbol, barlist[-2])
                hist = self._bars.setdefault(symbol, [])
                if not hist or completed.ts > hist[-1].ts:
                    hist.append(completed)
                    if self.on_bar:
                        asyncio.create_task(self.on_bar(completed, True))
            if barlist and self.on_bar:
                asyncio.create_task(self.on_bar(_to_bar(symbol, barlist[-1]), False))

        bars.updateEvent += on_update

    def history(self, symbol: str) -> list[Bar]:
        out = list(self._bars.get(symbol, []))
        live = self._live_bars.get(symbol)
        if live and len(live) > 0:
            current = _to_bar(symbol, live[-1])
            if not out or current.ts > out[-1].ts:
                out.append(current)
        return out


# -- helpers --------------------------------------------------------------------------


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _num(v) -> bool:
    return v is not None and v == v and v > 0  # filters None and NaN


def _ticker_price(ticker) -> Optional[float]:
    for v in (ticker.last, ticker.marketPrice(), ticker.close):
        if _num(v):
            return float(v)
    return None


def _to_bar(symbol: str, b) -> Bar:
    ts = b.date.timestamp() if hasattr(b.date, "timestamp") else float(b.date)
    return Bar(
        symbol=symbol, ts=ts,
        open=float(b.open), high=float(b.high), low=float(b.low), close=float(b.close),
        volume=int(b.volume or 0), timeframe="1m",
    )


def _parse_float_shares(xml_report: str) -> Optional[int]:
    """Extract total float from the ReportSnapshot XML, if present."""
    try:
        root = ET.fromstring(xml_report)
        el = root.find(".//SharesOut")
        if el is not None:
            total_float = el.get("TotalFloat")
            if total_float:
                return int(float(total_float))
    except Exception:
        pass
    return None
