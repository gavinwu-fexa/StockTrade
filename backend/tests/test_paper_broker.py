import pytest

from app.brokers.paper import PaperBroker
from app.models import OrderRequest, OrderSide, OrderStatus, OrderType, Quote


def quote(symbol="TEST", bid=4.99, ask=5.01, last=5.00, ts=100.0):
    return Quote(symbol=symbol, ts=ts, bid=bid, ask=ask, last=last)


@pytest.mark.asyncio
async def test_market_buy_fills_at_ask_plus_slippage():
    b = PaperBroker(starting_cash=5000, slippage=0.01)
    await b.update_quote(quote())
    order = await b.submit(OrderRequest(symbol="TEST", side=OrderSide.BUY, qty=100))
    assert order.status == OrderStatus.FILLED
    assert order.avg_fill_price == 5.02
    assert b.positions()[0].qty == 100
    assert b.cash == pytest.approx(5000 - 502)


@pytest.mark.asyncio
async def test_rejects_without_market_data():
    b = PaperBroker()
    order = await b.submit(OrderRequest(symbol="NOPE", side=OrderSide.BUY, qty=100))
    assert order.status == OrderStatus.REJECTED


@pytest.mark.asyncio
async def test_round_trip_records_trade():
    b = PaperBroker(starting_cash=5000)
    closed = []

    async def on_closed(t):
        closed.append(t)

    b.on_trade_closed = on_closed
    await b.update_quote(quote())
    await b.submit(OrderRequest(symbol="TEST", side=OrderSide.BUY, qty=100))
    await b.update_quote(quote(bid=5.49, ask=5.51, last=5.50, ts=200.0))
    await b.submit(OrderRequest(symbol="TEST", side=OrderSide.SELL, qty=100))
    assert len(closed) == 1
    assert closed[0].pnl > 0
    assert b.positions() == []


@pytest.mark.asyncio
async def test_limit_buy_rests_until_touched():
    b = PaperBroker(starting_cash=5000)
    await b.update_quote(quote())
    order = await b.submit(OrderRequest(
        symbol="TEST", side=OrderSide.BUY, qty=100,
        type=OrderType.LIMIT, limit_price=4.90,
    ))
    assert order.status == OrderStatus.SUBMITTED
    assert len(b.open_orders()) == 1
    await b.update_quote(quote(bid=4.85, ask=4.88, last=4.86, ts=150.0))
    assert order.status == OrderStatus.FILLED
    assert order.avg_fill_price <= 4.90
    assert b.open_orders() == []


@pytest.mark.asyncio
async def test_flatten_sells_everything():
    b = PaperBroker(starting_cash=10_000)
    await b.update_quote(quote("AAA"))
    await b.update_quote(quote("BBB", ts=101.0))
    await b.submit(OrderRequest(symbol="AAA", side=OrderSide.BUY, qty=100))
    await b.submit(OrderRequest(symbol="BBB", side=OrderSide.BUY, qty=50))
    orders = await b.flatten()
    assert len(orders) == 2
    assert b.positions() == []


@pytest.mark.asyncio
async def test_sell_without_position_rejected():
    b = PaperBroker()
    await b.update_quote(quote())
    order = await b.submit(OrderRequest(symbol="TEST", side=OrderSide.SELL, qty=100))
    assert order.status == OrderStatus.REJECTED
