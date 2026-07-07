"""Historical data sources for backtesting.

SIM mode ships with a synthetic generator that produces momentum-day tapes
(gap, surges, micro pullbacks, fades) so strategies can be exercised without
market-data subscriptions. When connected to IBKR, `fetch_ibkr_history`
downloads real intraday bars through the same interface.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

from ..models import Bar


def generate_momentum_day(
    symbol: str = "SIM",
    seed: int = 1,
    bars: int = 390,
    start_price: float = 5.0,
    timeframe_sec: int = 60,
    day_index: int = 0,
) -> list[Bar]:
    """A synthetic small-cap momentum day: gap-up open, morning surges with
    micro pullbacks, midday fade — the tape Ross's setups live on.

    day_index shifts the session forward one calendar day at a time so
    multi-day backtests get strictly increasing timestamps."""
    rng = random.Random(seed)
    base = int(time.time() // 86400) * 86400 - 30 * 86400  # 30 days ago 00:00 UTC
    start_ts = base + day_index * 86400 + 13 * 3600  # ~9am

    out: list[Bar] = []
    price = start_price * rng.uniform(1.05, 1.25)   # gap up
    phase_ticks = 0
    phase = "surge"
    momentum = rng.uniform(0.0015, 0.004)

    for i in range(bars):
        phase_ticks -= 1
        if phase_ticks <= 0:
            morning = i < bars * 0.45
            if phase == "surge":
                phase = "pullback"
                phase_ticks = rng.randint(2, 5)
            else:
                phase = "surge" if (morning or rng.random() < 0.35) else "fade"
                phase_ticks = rng.randint(6, 18) if phase == "surge" else rng.randint(10, 30)

        drift = {"surge": momentum, "pullback": -momentum * 0.6, "fade": -momentum * 0.35}[phase]
        o = price
        c = max(0.5, o * (1 + drift + rng.gauss(0, 0.0035)))
        hi = max(o, c) * (1 + abs(rng.gauss(0, 0.002)))
        lo = min(o, c) * (1 - abs(rng.gauss(0, 0.002)))
        vol_mult = {"surge": 3.5, "pullback": 1.2, "fade": 0.8}[phase]
        vol = int(rng.uniform(0.5, 1.6) * vol_mult * 20_000)
        out.append(Bar(
            symbol=symbol, ts=start_ts + i * timeframe_sec,
            open=round(o, 2), high=round(hi, 2), low=round(lo, 2), close=round(c, 2),
            volume=vol, timeframe="1m",
        ))
        price = c
    return out


CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "bars_cache"


def _cache_path(symbol: str, duration: str, bar_size: str) -> Path:
    day = time.strftime("%Y-%m-%d")
    key = f"{symbol}_{duration}_{bar_size}_{day}".replace(" ", "")
    return CACHE_DIR / f"{key}.json"


async def fetch_ibkr_history(
    symbol: str,
    duration: str = "5 D",
    bar_size: str = "1 min",
    ib=None,
) -> list[Bar]:
    """Download historical bars from IBKR, cached to disk per (symbol, day).

    Reuses a connected `ib` instance when provided (PAPER mode); otherwise
    opens a short-lived connection of its own.
    """
    cache = _cache_path(symbol, duration, bar_size)
    if cache.exists():
        raw = json.loads(cache.read_text())
        return [Bar(**b) for b in raw]

    import asyncio

    # bind ib_insync to the loop we're actually running on (see brokers/ibkr.py)
    asyncio.set_event_loop(asyncio.get_running_loop())
    from ib_insync import IB, Stock

    from ..config import settings

    own_connection = ib is None
    if own_connection:
        # Historical data is read-only, so probing live ports here is safe.
        ib = IB()
        last_err: Exception = ConnectionError("no IBKR ports configured")
        for port in [*settings.ibkr.paper_ports, *settings.ibkr.live_ports]:
            try:
                await asyncio.wait_for(
                    ib.connectAsync(
                        settings.ibkr.host, port,
                        clientId=settings.ibkr.client_id + 1,
                    ),
                    timeout=5,
                )
                break
            except (asyncio.TimeoutError, OSError) as e:
                last_err = e
        else:
            raise ConnectionError(str(last_err))
    try:
        contracts = await ib.qualifyContractsAsync(Stock(symbol, "SMART", "USD"))
        if not contracts:
            raise ValueError(f"Unknown symbol {symbol}")
        ib_bars = await ib.reqHistoricalDataAsync(
            contracts[0],
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=False,
        )
        bars = [
            Bar(
                symbol=symbol,
                ts=b.date.timestamp(),
                open=b.open, high=b.high, low=b.low, close=b.close,
                volume=int(b.volume), timeframe="1m",
            )
            for b in ib_bars
        ]
        if bars:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps([b.model_dump() for b in bars]))
        return bars
    finally:
        if own_connection:
            ib.disconnect()
