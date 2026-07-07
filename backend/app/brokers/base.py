"""Broker abstraction. PaperBroker (simulator) and IBKRBroker implement this."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Optional

from ..models import AccountState, Fill, Order, OrderRequest, Position, Quote

FillCallback = Callable[[Fill], Awaitable[None]]
QuoteCallback = Callable[[Quote], Awaitable[None]]


class Broker(ABC):
    def __init__(self):
        self.on_fill: Optional[FillCallback] = None
        self.on_quote: Optional[QuoteCallback] = None

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def submit(self, req: OrderRequest) -> Order: ...

    @abstractmethod
    async def cancel(self, order_id: str) -> bool: ...

    @abstractmethod
    async def cancel_all(self) -> int: ...

    @abstractmethod
    async def flatten(self, symbol: Optional[str] = None) -> list[Order]:
        """Market-sell open position(s); all symbols when symbol is None."""

    @abstractmethod
    def positions(self) -> list[Position]: ...

    @abstractmethod
    def account(self) -> AccountState: ...

    @abstractmethod
    def open_orders(self) -> list[Order]: ...
