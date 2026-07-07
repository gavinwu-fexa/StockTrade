from app.backtest.data import generate_momentum_day
from app.backtest.engine import BacktestEngine
from app.backtest.metrics import compute_metrics
from app.models import Bar, TradeRecord
from app.strategies import STRATEGY_REGISTRY


def test_synthetic_day_shape():
    bars = generate_momentum_day(seed=7)
    assert len(bars) == 390
    assert all(b.high >= max(b.open, b.close) for b in bars)
    assert all(b.low <= min(b.open, b.close) for b in bars)
    # deterministic per seed
    again = generate_momentum_day(seed=7)
    assert [b.close for b in bars] == [b.close for b in again]


def run_strategy(name: str, days: int = 3):
    bars = []
    for d in range(days):
        bars.extend(generate_momentum_day(seed=100 + d, day_index=d))
    strategy = STRATEGY_REGISTRY[name]()
    return BacktestEngine(strategy, starting_equity=5000).run(bars)


def test_ema_cross_produces_trades():
    result = run_strategy("ema_cross")
    assert result.metrics["trades"] > 0
    assert result.metrics["ending_equity"] == 5000 + result.metrics["total_pnl"]


def test_macd_cross_produces_trades():
    result = run_strategy("macd_cross")
    assert result.metrics["trades"] > 0


def test_micro_pullback_runs():
    result = run_strategy("micro_pullback", days=5)
    # entries are selective; just require it runs and any trades are recorded coherently
    for t in result.trades:
        assert t.exit_ts >= t.entry_ts
        assert t.qty > 0


def test_all_registered_strategies_backtestable():
    for name in STRATEGY_REGISTRY:
        result = run_strategy(name, days=2)
        assert "win_rate" in result.metrics


def test_metrics_math():
    trades = [
        TradeRecord(symbol="T", entry_ts=1, exit_ts=2, entry_price=5, exit_price=6, qty=100, pnl=100),
        TradeRecord(symbol="T", entry_ts=3, exit_ts=4, entry_price=5, exit_price=4.5, qty=100, pnl=-50),
        TradeRecord(symbol="T", entry_ts=5, exit_ts=6, entry_price=5, exit_price=6, qty=100, pnl=100),
    ]
    m = compute_metrics(trades, 1000)
    assert m["trades"] == 3
    assert m["win_rate"] == 66.7
    assert m["avg_win"] == 100
    assert m["avg_loss"] == 50
    assert m["pl_ratio"] == 2.0
    assert m["total_pnl"] == 150
    assert m["max_consecutive_losses"] == 1
