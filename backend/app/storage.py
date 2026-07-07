"""SQLite persistence for trades, fills, and backtest runs.

Kept deliberately simple: synchronous sqlite3 with short transactions —
call volumes here are tiny (a few writes per trade). The DB file lives in
backend/data/stocktrade.db.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .models import Fill, TradeRecord

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "stocktrade.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    entry_ts REAL NOT NULL,
    exit_ts REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    qty INTEGER NOT NULL,
    pnl REAL NOT NULL,
    entry_reason TEXT DEFAULT '',
    exit_reason TEXT DEFAULT '',
    mode TEXT DEFAULT 'sim',
    day TEXT NOT NULL              -- YYYY-MM-DD local, for daily P&L queries
);
CREATE INDEX IF NOT EXISTS idx_trades_day ON trades(day);

CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty INTEGER NOT NULL,
    price REAL NOT NULL,
    ts REAL NOT NULL,
    mode TEXT DEFAULT 'sim'
);

CREATE TABLE IF NOT EXISTS backtests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    strategy TEXT NOT NULL,
    params TEXT NOT NULL,          -- JSON
    data_source TEXT NOT NULL,     -- 'synthetic' | 'ibkr'
    symbol TEXT,
    days INTEGER,
    metrics TEXT NOT NULL          -- JSON (without equity curve/trades)
);
"""


def _day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


class Storage:
    def __init__(self, path: Path = DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- trades ---------------------------------------------------------------

    def record_trade(self, trade: TradeRecord, mode: str) -> None:
        self._conn.execute(
            "INSERT INTO trades (symbol, entry_ts, exit_ts, entry_price, exit_price,"
            " qty, pnl, entry_reason, exit_reason, mode, day)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (trade.symbol, trade.entry_ts, trade.exit_ts, trade.entry_price,
             trade.exit_price, trade.qty, trade.pnl, trade.entry_reason,
             trade.exit_reason, mode, _day(trade.exit_ts)),
        )
        self._conn.commit()

    def trades(self, day: Optional[str] = None, limit: int = 500) -> list[dict]:
        if day:
            rows = self._conn.execute(
                "SELECT * FROM trades WHERE day = ? ORDER BY exit_ts DESC LIMIT ?",
                (day, limit),
            )
        else:
            rows = self._conn.execute(
                "SELECT * FROM trades ORDER BY exit_ts DESC LIMIT ?", (limit,),
            )
        return [dict(r) for r in rows.fetchall()]

    def day_pnl(self, day: str, mode: str) -> tuple[float, int]:
        """(realized pnl, consecutive losers ending the day) for risk restore."""
        rows = self._conn.execute(
            "SELECT pnl FROM trades WHERE day = ? AND mode = ? ORDER BY exit_ts",
            (day, mode),
        ).fetchall()
        total = sum(r["pnl"] for r in rows)
        streak = 0
        for r in rows:
            if r["pnl"] < 0:
                streak += 1
            elif r["pnl"] > 0:
                streak = 0
        return total, streak

    def daily_summary(self, limit: int = 30) -> list[dict]:
        rows = self._conn.execute(
            "SELECT day, mode, COUNT(*) AS trades, ROUND(SUM(pnl), 2) AS pnl,"
            " SUM(pnl > 0) AS wins"
            " FROM trades GROUP BY day, mode ORDER BY day DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows.fetchall()]

    # -- fills ----------------------------------------------------------------

    def record_fill(self, fill: Fill, mode: str) -> None:
        self._conn.execute(
            "INSERT INTO fills (order_id, symbol, side, qty, price, ts, mode)"
            " VALUES (?,?,?,?,?,?,?)",
            (fill.order_id, fill.symbol, fill.side.value, fill.qty, fill.price,
             fill.ts, mode),
        )
        self._conn.commit()

    def fills(self, limit: int = 200) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM fills ORDER BY ts DESC LIMIT ?", (limit,),
        )
        return [dict(r) for r in rows.fetchall()]

    # -- backtests ------------------------------------------------------------

    def record_backtest(self, strategy: str, params: dict, data_source: str,
                        symbol: Optional[str], days: int, metrics: dict) -> int:
        slim = {k: v for k, v in metrics.items() if k != "equity_curve"}
        cur = self._conn.execute(
            "INSERT INTO backtests (ts, strategy, params, data_source, symbol, days, metrics)"
            " VALUES (?,?,?,?,?,?,?)",
            (time.time(), strategy, json.dumps(params), data_source, symbol,
             days, json.dumps(slim)),
        )
        self._conn.commit()
        return int(cur.lastrowid or 0)

    def backtests(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM backtests ORDER BY ts DESC LIMIT ?", (limit,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["params"] = json.loads(d["params"])
            d["metrics"] = json.loads(d["metrics"])
            out.append(d)
        return out

    def close(self) -> None:
        self._conn.close()


_storage: Optional[Storage] = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage
