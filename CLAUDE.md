# StockTrade — notes for Claude

Personal day-trading app (Ross Cameron small-account momentum). Full design in
ARCHITECTURE.md; strategy criteria sourced from the Warrior Trading Small
Account Tool Kit PDF.

## Commands
- Backend tests: `cd backend && .venv/bin/python -m pytest tests -q`
- Frontend typecheck: `cd frontend && ./node_modules/.bin/tsc -b`
- Dev servers: use `.claude/launch.json` (backend :8000, frontend :5173),
  or `make backend` / `make frontend`.
- Python is the venv at `backend/.venv` (3.12) — NOT system python (3.9).
- Node/npm are at `/opt/homebrew/bin`.

## Architecture invariants
- Strategies are pure signal generators (`on_bar` → `Signal[]`); they never
  touch brokers. The same instance code must run in backtest and live.
- Every order (hotkey or strategy) goes through `RiskManager.approve` —
  exits/sells are never blocked, buys are sized/vetoed.
- New strategies/pickers register via decorator + import in the package
  `__init__.py`; the UI discovers them from `/api/state`.
- SIM mode must keep working with zero external dependencies (no IBKR, no
  market data). PAPER (IBKR paper account) is runtime-switchable from the UI;
  LIVE requires editing config, deliberately.
- READ-ONLY safeguard: connecting to a live IBKR port (7496/4001, see
  `IBKRConfig.live_ports`) forces `broker.read_only = True` — submit/flatten/
  cancel refuse at the broker AND engine layers. There is no override switch;
  never add one. Gavin's real account is reachable on Gateway port 4001.
- ib_insync sync methods like `IB.accountSummary()` are NOT cache reads —
  they re-enter the event loop and deadlock under uvicorn. Use
  `accountValues()`/`positions()`/`openTrades()` (pure caches) or the
  `*Async` variants.
- IBKR percent-change: use `ticker.close` (prior session close) as
  prev_close; exclude today's partial daily bar from 30-day averages.
- Feeds (`app/feeds/`) are the data abstraction: SimFeed and IbkrFeed emit the
  same quote/bar/snapshot events; the engine must stay feed-agnostic.
- ib_insync must bind to the running event loop: uvicorn runs with
  `--loop asyncio`, and any code instantiating `IB()` first calls
  `asyncio.set_event_loop(asyncio.get_running_loop())` — otherwise
  "attached to a different loop" errors.
- Trades/fills/backtests persist to SQLite via `app/storage.py`; the engine
  rehydrates today's P&L + loser streak into RiskManager on startup so
  restarts can't reset the daily loss limit.
- WebSocket bar events must be emitted in ascending timestamp order —
  lightweight-charts hard-asserts on ordering (completed bar before the
  newer in-progress bar; frontend `upsertBar` is the defensive layer).
- SIM "1-min" bars close every 5 wall-clock seconds (SIM_BAR_SEC) so
  indicators develop at demo speed.
