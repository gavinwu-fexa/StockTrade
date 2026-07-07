import time

import pytest

from app.config import Mode
from app.engine import RoundTrips
from app.models import Fill, OrderSide


def fill(side: OrderSide, qty: int, price: float, ts: float = None) -> Fill:
    return Fill(order_id="x", symbol="TEST", side=side, qty=qty, price=price,
                ts=ts or time.time())


def test_round_trips_simple():
    rt = RoundTrips()
    assert rt.add_fill(fill(OrderSide.BUY, 100, 5.00)) is None
    trade = rt.add_fill(fill(OrderSide.SELL, 100, 5.50))
    assert trade is not None
    assert trade.pnl == 50.0
    assert trade.qty == 100


def test_round_trips_scale_in_and_partial_out():
    rt = RoundTrips()
    rt.add_fill(fill(OrderSide.BUY, 100, 5.00))
    rt.add_fill(fill(OrderSide.BUY, 100, 6.00))     # avg 5.50
    assert rt.add_fill(fill(OrderSide.SELL, 100, 6.00)) is None  # still 100 left
    trade = rt.add_fill(fill(OrderSide.SELL, 100, 5.00))
    assert trade is not None
    # realized: 100*(6-5.5) + 100*(5-5.5) = 0
    assert trade.pnl == 0.0


def test_round_trips_ignores_sell_without_position():
    rt = RoundTrips()
    assert rt.add_fill(fill(OrderSide.SELL, 100, 5.00)) is None


@pytest.mark.asyncio
async def test_live_mode_switch_is_refused():
    from app.engine import Engine

    eng = Engine()
    with pytest.raises(ValueError):
        await eng.switch_mode(Mode.LIVE)
