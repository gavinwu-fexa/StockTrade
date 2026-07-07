# StockTrade

Personal day-trading app implementing Ross Cameron's small-account momentum
strategy (Warrior Trading Small Account Tool Kit), with pluggable stock pickers,
pluggable entry/exit strategies (MACD cross, EMA cross, micro pullback),
backtesting, hotkey execution, and an Interactive Brokers adapter.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

## Quick start

```bash
make setup      # one-time: python venv + npm install
make backend    # FastAPI on :8000 (SIM mode — synthetic market, paper fills)
make frontend   # Vite dev server on :5173
```

Open http://localhost:5173. The app boots in **SIM mode**: a synthetic tape of
low-float gappers drives the scanner, chart, strategies, and paper broker — no
IBKR connection or market-data subscription needed.

Run tests: `make test`

## Trading with hotkeys

Press `?` in the app for the full list. Highlights:

| Key | Action |
|-----|--------|
| `⇧B` | Buy market at current share size |
| `⇧S` | Sell half position |
| `⇧F` | Flatten current symbol |
| `⇧X` ×2 | Panic: flatten everything + cancel all |
| `B` / `S` | Stage limit order at ask/bid, `↑↓` to nudge, `⏎` to send |
| `1–4` | Share size = 25/50/75/100% of cash |
| `Tab` | Cycle scanner symbols |

## The Ross Cameron criteria (scanner)

A stock is **A-quality** when all five pass: relative volume ≥ 5x, up ≥ 10% on
the day, price $1–$20 ($5–$10 sweet spot), float < 20M (hot market) / 10M
(cold), and a news catalyst. The scanner grades A/B/C and shows each criterion
check per symbol.

Risk rules from the trading plan are enforced centrally: ~5% account risk per
trade sized off the stop, 2:1 profit-to-loss targets, 10% daily max loss halt,
and a halt after 3 consecutive losers (click the halt banner to re-arm).

## Adding a strategy

Create `backend/app/strategies/my_strategy.py`:

```python
from ..models import Bar, Signal, SignalType
from .base import Strategy, StrategyContext, register_strategy

@register_strategy
class MyStrategy(Strategy):
    name = "my_strategy"
    label = "My Strategy"
    default_params = {"window": 10}

    def on_bar(self, ctx: StrategyContext, bar: Bar) -> list[Signal]:
        ema = ctx.ema(self.params["window"]).update(bar.close)
        ...
        return []
```

Import it in `strategies/__init__.py`. It immediately appears in the UI's
strategy dropdown and the backtester — same code runs live and in backtests.

Stock pickers work the same way (`scanners/base.py` → `@register_picker`).

## Connecting Interactive Brokers (paper)

1. Start **TWS** (or IB Gateway) and log into your **paper** account.
2. Enable API access: File → Global Configuration → API → Settings →
   check *Enable ActiveX and Socket Clients*; port **7497** (TWS paper default).
   Add `127.0.0.1` to trusted IPs if prompted.
3. Click **PAPER** in the app header. That's it — the scanner switches to
   IBKR's top-percent-gainers ($1–$20), the chart streams real 1-min bars,
   and hotkey orders route to your paper account through the same risk gate.

Ports are probed automatically: TWS paper 7497, Gateway paper 4002. You can
pass an explicit port via `POST /api/mode {"mode":"paper","port":N}`.

**Live-account safeguard:** connecting to a live port (TWS 7496 / Gateway
4001) is allowed for *market data only* — the header shows
"🔒 DATA ONLY — LIVE ACCT" and every order path (buy, sell, flatten,
cancel) is refused at both the engine and broker layers. There is no
override; to trade, connect to a paper port.

Notes: without paid market-data subscriptions IBKR serves delayed quotes;
without fundamentals, float shows "unknown" (soft pass) and catalyst
detection is off, so the best scanner grade is B. `LIVE` trading
deliberately has no runtime path — it requires editing
`backend/app/config.py`.

## Persistence & backtests on real data

Trades, fills, and backtest runs persist to SQLite
(`backend/data/stocktrade.db`) — the **History** tab shows daily P&L and
past trades across restarts, and the daily loss limit survives a backend
bounce. In the **Backtest** tab, switch *Data* to “IBKR history (real
bars)”, enter any symbol, and the engine replays real 1-min bars (cached
locally) through the exact same strategy + risk code as live trading.
Strategy parameters (EMA windows, MACD periods, stops) are editable in the
UI — “params” next to the strategy selector.

## Layout

```
backend/   FastAPI + engine (scanners, strategies, risk, brokers, backtest)
frontend/  React + Vite UI (chart, scanner, hotkeys, backtest panel)
```
