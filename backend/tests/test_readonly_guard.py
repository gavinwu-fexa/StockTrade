"""The read-only safeguard: a broker connected to a live IBKR port must
refuse every order path, and the engine must refuse before even reaching
the broker."""
import pytest

from app.brokers.ibkr import IBKRBroker
from app.config import IBKRConfig
from app.models import OrderRequest, OrderSide, OrderStatus


def make_readonly_broker() -> IBKRBroker:
    b = IBKRBroker(IBKRConfig(), port=4001)
    b.read_only = True          # what connect() sets for live ports
    b.connected_port = 4001
    return b


def test_live_ports_config():
    cfg = IBKRConfig()
    assert 4001 in cfg.live_ports
    assert 7496 in cfg.live_ports
    assert set(cfg.paper_ports).isdisjoint(cfg.live_ports)


@pytest.mark.asyncio
async def test_submit_refused_when_read_only():
    b = make_readonly_broker()
    order = await b.submit(OrderRequest(symbol="AAPL", side=OrderSide.BUY, qty=1))
    assert order.status == OrderStatus.REJECTED
    assert "READ-ONLY" in order.reject_reason
    # sells refused too — this is someone's real account
    order = await b.submit(OrderRequest(symbol="AAPL", side=OrderSide.SELL, qty=1))
    assert order.status == OrderStatus.REJECTED


@pytest.mark.asyncio
async def test_flatten_and_cancels_refused_when_read_only():
    b = make_readonly_broker()
    assert await b.flatten() == []
    assert await b.cancel("1") is False
    assert await b.cancel_all() == 0


@pytest.mark.asyncio
async def test_engine_place_order_refuses_read_only():
    from app.engine import Engine

    eng = Engine()
    eng.broker = make_readonly_broker()
    result = await eng.place_order(OrderRequest(symbol="AAPL", side=OrderSide.BUY, qty=1))
    assert result["ok"] is False
    assert "READ-ONLY" in result["error"]
