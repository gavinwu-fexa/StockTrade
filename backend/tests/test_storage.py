import time

from app.models import Fill, OrderSide, TradeRecord
from app.storage import Storage


def make_storage(tmp_path):
    return Storage(tmp_path / "test.db")


def trade(pnl: float, ts: float = None) -> TradeRecord:
    ts = ts or time.time()
    return TradeRecord(
        symbol="TEST", entry_ts=ts - 60, exit_ts=ts,
        entry_price=5.0, exit_price=5.0 + pnl / 100, qty=100, pnl=pnl,
        entry_reason="test", exit_reason="test",
    )


def test_trades_persist_and_filter_by_day(tmp_path):
    s = make_storage(tmp_path)
    s.record_trade(trade(100), "sim")
    s.record_trade(trade(-50), "sim")
    today = time.strftime("%Y-%m-%d")
    assert len(s.trades()) == 2
    assert len(s.trades(day=today)) == 2
    assert len(s.trades(day="1999-01-01")) == 0


def test_day_pnl_and_streak_restore(tmp_path):
    s = make_storage(tmp_path)
    now = time.time()
    for pnl in (100, -10, -20):
        s.record_trade(trade(pnl, now), "sim")
    total, streak = s.day_pnl(time.strftime("%Y-%m-%d"), "sim")
    assert total == 70
    assert streak == 2
    # different mode isolated
    total_paper, _ = s.day_pnl(time.strftime("%Y-%m-%d"), "paper")
    assert total_paper == 0


def test_fills_roundtrip(tmp_path):
    s = make_storage(tmp_path)
    s.record_fill(Fill(order_id="1", symbol="TEST", side=OrderSide.BUY,
                       qty=100, price=5.0, ts=time.time()), "sim")
    fills = s.fills()
    assert len(fills) == 1
    assert fills[0]["side"] == "buy"


def test_backtest_history(tmp_path):
    s = make_storage(tmp_path)
    rid = s.record_backtest("macd_cross", {"fast": 12}, "synthetic", "SIM", 5,
                            {"trades": 7, "win_rate": 40.0, "equity_curve": [1, 2]})
    assert rid > 0
    runs = s.backtests()
    assert runs[0]["strategy"] == "macd_cross"
    assert "equity_curve" not in runs[0]["metrics"]

    summary = s.daily_summary()
    assert summary == []  # no trades recorded in this test
