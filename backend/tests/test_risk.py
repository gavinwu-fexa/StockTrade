from app.config import RiskConfig
from app.models import AccountState, OrderRequest, OrderSide, TradeRecord
from app.risk.manager import RiskManager


def make_trade(pnl: float) -> TradeRecord:
    return TradeRecord(
        symbol="TEST", entry_ts=0, exit_ts=1,
        entry_price=5.0, exit_price=5.0 + pnl / 100, qty=100, pnl=pnl,
    )


def make_rm(equity=5000.0):
    return RiskManager(RiskConfig(), starting_equity=equity)


def test_position_sizing_from_stop_distance():
    rm = make_rm()
    # risk 5% of 5000 = $250; stop $0.25 below → 1000 shares, capped by notional
    qty, stop, target = rm.size_position(5000, entry=5.00, stop=4.75)
    assert stop == 4.75
    assert target == 5.50            # 2:1
    assert qty == min(1000, int(5000 / 5.00))


def test_daily_max_loss_halts():
    rm = make_rm()
    rm.record_trade(make_trade(-501))   # > 10% of 5000
    assert rm.halted
    assert "max loss" in rm.halt_reason.lower()


def test_three_consecutive_losers_halts():
    rm = make_rm()
    for _ in range(3):
        rm.record_trade(make_trade(-10))
    assert rm.halted
    assert "consecutive" in rm.halt_reason


def test_winner_resets_streak():
    rm = make_rm()
    rm.record_trade(make_trade(-10))
    rm.record_trade(make_trade(-10))
    rm.record_trade(make_trade(50))
    rm.record_trade(make_trade(-10))
    assert not rm.halted
    assert rm.consecutive_losers == 1


def test_halted_blocks_buys_but_not_sells():
    rm = make_rm()
    rm.halted = True
    rm.halt_reason = "test"
    acct = AccountState(equity=5000, cash=5000)
    buy = rm.approve(OrderRequest(symbol="T", side=OrderSide.BUY, qty=100), acct, 5.0)
    sell = rm.approve(OrderRequest(symbol="T", side=OrderSide.SELL, qty=100), acct, 5.0)
    assert not buy.approved
    assert sell.approved


def test_oversized_order_clamped():
    rm = make_rm()
    acct = AccountState(equity=5000, cash=5000)
    decision = rm.approve(
        OrderRequest(symbol="T", side=OrderSide.BUY, qty=100_000), acct, 5.0,
        stop_price=4.75,
    )
    assert decision.approved
    assert decision.qty <= 1000
    assert decision.warnings


def test_rearm_clears_halt():
    rm = make_rm()
    for _ in range(3):
        rm.record_trade(make_trade(-10))
    assert rm.halted
    rm.rearm()
    assert not rm.halted
