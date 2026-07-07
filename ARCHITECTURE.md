# StockTrade — Architecture

A personal day-trading application implementing Ross Cameron's small-account momentum
strategy, with pluggable stock pickers, pluggable entry/exit strategies, backtesting,
and live execution through Interactive Brokers.

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Frontend (React + Vite)                       │
│  Scanner Watchlist │ Candlestick Chart │ Order Panel │ Positions/P&L   │
│           Hotkey engine (buy/sell/flatten/cancel, share-size presets)  │
└──────────────▲───────────────────────────────▲────────────────────────┘
               │ REST (setup/config/backtest)  │ WebSocket (quotes, bars,
               │                               │  scanner hits, fills, P&L)
┌──────────────┴───────────────────────────────┴────────────────────────┐
│                        Backend (Python + FastAPI)                      │
│                                                                        │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐  │
│  │  Scanners   │  │  Strategies  │  │    Risk     │  │  Backtester  │  │
│  │ (pluggable) │  │ (pluggable)  │  │   Manager   │  │ (event-drvn) │  │
│  └──────┬──────┘  └──────┬───────┘  └──────┬──────┘  └──────┬───────┘  │
│         │                │                 │                │          │
│  ┌──────┴────────────────┴─────────────────┴────────────────┴───────┐  │
│  │                    Core: indicators, models, bus                 │  │
│  └──────────────────────────────┬───────────────────────────────────┘  │
│                                 │                                      │
│  ┌──────────────────────────────┴───────────────────────────────────┐  │
│  │                  Broker abstraction (pluggable)                  │  │
│  │   PaperBroker (simulator, default)  │  IBKRBroker (ib_insync)    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

## Design principles

1. **Everything trading-related is a plugin.** Stock pickers, strategies, and brokers
   each implement a small abstract interface and register themselves in a registry.
   Adding a new strategy = one new file, zero changes elsewhere.
2. **Same strategy code runs live and in backtest.** Strategies consume `Bar` events
   and emit `Signal`s. The backtest engine and the live engine feed them identically.
3. **Paper-first.** The `PaperBroker` simulates fills so the entire app works with no
   IBKR account connected. Flipping to live is a config change.
4. **Risk is enforced centrally**, not per-strategy. The `RiskManager` sits between
   signals and the broker and can veto or resize any order.

## Directory layout

```
StockTrade/
├── ARCHITECTURE.md          ← this file
├── README.md                ← quick start
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py          ← FastAPI app, WebSocket hub
│   │   ├── engine.py        ← wires feed+broker+strategy+risk; mode switching
│   │   ├── config.py        ← account size, risk params, broker selection
│   │   ├── storage.py       ← SQLite: trades, fills, backtest runs (data/stocktrade.db)
│   │   ├── models.py        ← Bar, Quote, Order, Position, Signal, ScannerResult
│   │   ├── indicators.py    ← EMA, SMA, MACD, VWAP, relative volume
│   │   ├── feeds/
│   │   │   ├── base.py      ← DataFeed ABC (quotes, bars, scanner snapshots)
│   │   │   ├── sim.py       ← synthetic momentum tape (SIM mode)
│   │   │   └── ibkr.py      ← IBKR scanner/quotes/bars via ib_insync (PAPER mode)
│   │   ├── scanners/
│   │   │   ├── base.py      ← StockPicker ABC + registry
│   │   │   └── ross_cameron.py  ← the criteria from the Warrior Trading doc
│   │   ├── strategies/
│   │   │   ├── base.py      ← Strategy ABC + registry
│   │   │   ├── ema_cross.py     ← EMA fast/slow crossover (configurable windows)
│   │   │   ├── macd_cross.py    ← MACD/signal-line cross entries & exits
│   │   │   └── micro_pullback.py← Ross's primary setup: dip-buy on front side
│   │   ├── risk/
│   │   │   └── manager.py   ← 2:1 R/R sizing, daily max loss, consecutive-loser halt
│   │   ├── brokers/
│   │   │   ├── base.py      ← Broker ABC
│   │   │   ├── paper.py     ← simulated fills against live/sim quotes
│   │   │   └── ibkr.py      ← Interactive Brokers via ib_insync (TWS / IB Gateway)
│   │   ├── backtest/
│   │   │   ├── engine.py    ← event-driven bar replay
│   │   │   ├── metrics.py   ← win rate, P/L ratio, drawdown, expectancy
│   │   │   └── data.py      ← historical bars (IBKR download or synthetic)
│   │   ├── sim/
│   │   │   └── market.py    ← synthetic momentum-stock simulator (dev mode)
│   │   └── api/
│   │       ├── routes.py    ← REST: scanner, strategies, backtests, config
│   │       └── ws.py        ← WebSocket: bars, quotes, fills, positions, alerts
│   └── tests/
└── frontend/
    ├── package.json
    └── src/
        ├── App.tsx
        ├── state/store.ts       ← app state (zustand)
        ├── api/client.ts        ← REST + WS client (auto-reconnect)
        ├── hotkeys/useHotkeys.ts← global shortcut engine
        └── components/
            ├── ScannerPanel.tsx     ← live gappers list w/ criteria badges
            ├── ChartPanel.tsx       ← candlesticks + EMA9/20 + MACD + VWAP + volume
            ├── OrderPanel.tsx       ← share size, limit/market, buying power
            ├── PositionsPanel.tsx   ← open positions, unrealized P&L
            ├── TradeLog.tsx         ← fills & signals feed
            ├── RiskBar.tsx          ← daily P&L vs max loss, loser streak
            └── HotkeyHelp.tsx       ← overlay listing all shortcuts (?)
```

## Core interfaces

### StockPicker (scanners/base.py)

```python
class StockPicker(ABC):
    name: str
    @abstractmethod
    def evaluate(self, snap: StockSnapshot) -> ScannerResult | None:
        """Return a scored result if the stock qualifies, else None."""
```

`RossCameronPicker.evaluate` scores each criterion from the Small Account Tool Kit:

| Criterion            | Requirement                                   |
|----------------------|-----------------------------------------------|
| Relative volume      | ≥ 5x 30-day average                           |
| Percent change       | ≥ +10% on the day                             |
| Price                | $1–$20 hard band, $5–$10 sweet spot           |
| Float                | < 20M shares (hot market), < 10M (cold)       |
| Catalyst             | breaking-news headline preferred              |

All five ⇒ **A-quality**; results are graded A/B/C and ranked. The scanner engine runs
every picker against the universe each tick and pushes results over the WebSocket.

### Strategy (strategies/base.py)

```python
class Strategy(ABC):
    name: str
    params: dict          # JSON-schema-described, editable from the UI
    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[Signal]: ...
```

`StrategyContext` exposes indicator series (lazily computed & cached), current
position, and account info. Signals are `ENTER_LONG / EXIT_LONG / SCALE_OUT` with a
reason string (shown in the UI and in backtest reports).

Included strategies:
- **EMACross** — fast EMA crosses above slow EMA ⇒ enter; crosses below ⇒ exit.
  Windows configurable (default 9/20 on 1-min).
- **MACDCross** — MACD line vs signal line (12/26/9 default). Per the trading plan,
  MACD crossing under signal is also a global *invalidation* exit.
- **MicroPullback** — Ross's primary small-account setup: strong up-move, first
  red-to-green micro dip on rising volume, entry over the pullback high, stop at
  pullback low, invalidated by MACD cross-down or fading volume.

### Broker (brokers/base.py)

```python
class Broker(ABC):
    async def connect(self): ...
    async def submit(self, order: OrderRequest) -> Order: ...
    async def cancel(self, order_id: str): ...
    async def cancel_all(self): ...
    async def flatten(self, symbol: str | None = None): ...
    def positions(self) -> list[Position]: ...
    def account(self) -> AccountState: ...
    # event callbacks: on_fill, on_quote, on_bar
```

`IBKRBroker` wraps **ib_insync** against TWS or IB Gateway (paper port 7497 / live
7496). `PaperBroker` fills market orders at the current ask/bid with configurable
slippage, so the full app runs standalone.

### RiskManager (risk/manager.py)

Gate between strategy/hotkey intents and the broker:

- **Position sizing**: risk ≈ 5% of account per trade; shares = risk$ / (entry − stop).
- **2:1 rule**: default profit target = 2 × stop distance.
- **Daily max loss**: 10% of account ⇒ trading disabled for the day.
- **Three consecutive losers** ⇒ trading halted (manual re-arm).
- Time-of-day window (default 7:00–11:00 ET) — outside it, new entries warn.

### Backtester (backtest/engine.py)

Event-driven replay: historical bars → strategy `on_bar` → simulated fills (next-bar
open, configurable slippage/commission) → `metrics.py` computes win rate, average
win/loss, P/L ratio, expectancy, max drawdown, equity curve. Results persisted as
JSON so the UI can list and compare runs.

## Hotkeys (defaults, remappable in `frontend/src/hotkeys/keymap.ts`)

| Key            | Action                                          |
|----------------|-------------------------------------------------|
| `Shift+B`      | Buy market, current share size                  |
| `Shift+S`      | Sell 1/2 position (market)                      |
| `Shift+F`      | Flatten current symbol (sell all, market)       |
| `Shift+X`      | FLATTEN EVERYTHING + cancel all orders (panic)  |
| `Shift+C`      | Cancel all open orders                          |
| `1 / 2 / 3 / 4`| Share-size presets (25% / 50% / 75% / 100%)     |
| `↑ / ↓`        | Nudge limit price by a cent                     |
| `B`            | Stage limit buy at ask (arm, Enter to send)     |
| `S`            | Stage limit sell at bid                         |
| `Enter`        | Send staged order                               |
| `Esc`          | Clear staged order                              |
| `Tab / Shift+Tab` | Cycle through scanner symbols                |
| `?`            | Show hotkey overlay                             |

Hotkeys always require the app window focused; destructive ones (`Shift+X`) flash a
confirmation toast for 500 ms during which a second press confirms — fast but not
accidental.

## Data flow (live)

1. Scanner engine polls market data (IBKR scanner subscription, or sim) → pickers
   evaluate → qualifying `ScannerResult`s pushed over WS → watchlist updates.
2. Selecting a symbol subscribes to its quotes + 1-min/5-min bars.
3. Active strategy consumes bars → emits signals → RiskManager sizes/vetoes →
   broker submits → fills stream back → positions/P&L update everywhere.
4. Manual hotkey trades go through the same RiskManager gate.

## Modes

- `SIM` (default): synthetic momentum tape, PaperBroker. No dependencies, demo-ready.
- `PAPER`: real IBKR market data + IBKR paper account (TWS port 7497). Switchable
  from the UI at runtime; the feed+broker pair swaps, everything else is identical.
- `LIVE`: real money (port 7496). Deliberately has **no runtime path** — requires
  editing config.py.

## Data feeds

`feeds/base.py` defines the DataFeed contract: quote events, bar events
(with a completed flag), and `snapshots()` for the scanner. `SimFeed`
synthesizes all three. `IbkrFeed` sources them from TWS/IB Gateway:
TOP_PERC_GAIN scanner polls ($1–$20 band), 30-day average volume and float
(fundamentals ReportSnapshot) cached per symbol per day, and 1-min bars via
`keepUpToDate` historical subscriptions. Without market-data/fundamentals
subscriptions the feed degrades gracefully: delayed quotes, unknown float
(soft-pass in the picker), no catalyst detection (max grade B).

## Persistence

`storage.py` (SQLite, `backend/data/stocktrade.db`): completed trades, fills,
and backtest run summaries, tagged by mode and day. On startup the engine
rehydrates today's realized P&L and consecutive-loser streak into the
RiskManager, so a backend restart can't reset the daily loss limit.
Backtests against IBKR history cache bars per (symbol, duration, day) under
`backend/data/bars_cache/`.
