"""Performance metrics for backtest runs — mirrors the 'Profit Trifecta'
goals in the tool kit: accuracy (win rate), P/L ratio, consistency."""
from __future__ import annotations

from ..models import TradeRecord


def compute_metrics(trades: list[TradeRecord], starting_equity: float) -> dict:
    if not trades:
        return {
            "trades": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "pl_ratio": 0.0, "expectancy": 0.0, "total_pnl": 0.0,
            "max_drawdown": 0.0, "max_drawdown_pct": 0.0, "equity_curve": [],
            "return_pct": 0.0, "max_consecutive_losses": 0,
        }

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(t.pnl for t in losses) / len(losses)) if losses else 0.0
    total_pnl = sum(t.pnl for t in trades)

    equity = starting_equity
    peak = equity
    max_dd = 0.0
    curve = [{"ts": trades[0].entry_ts, "equity": round(equity, 2)}]
    streak = 0
    max_streak = 0
    for t in trades:
        equity += t.pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        curve.append({"ts": t.exit_ts, "equity": round(equity, 2)})
        streak = streak + 1 if t.pnl <= 0 else 0
        max_streak = max(max_streak, streak)

    win_rate = len(wins) / len(trades)
    pl_ratio = (avg_win / avg_loss) if avg_loss > 0 else float(len(wins) > 0)
    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

    return {
        "trades": len(trades),
        "win_rate": round(win_rate * 100, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "pl_ratio": round(pl_ratio, 2),
        "expectancy": round(expectancy, 2),
        "total_pnl": round(total_pnl, 2),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd / starting_equity * 100, 2) if starting_equity else 0.0,
        "return_pct": round(total_pnl / starting_equity * 100, 2) if starting_equity else 0.0,
        "max_consecutive_losses": max_streak,
        "equity_curve": curve,
    }
