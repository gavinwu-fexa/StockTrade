"""StockPicker plugin interface.

To add a new stock-picking strategy:

    from .base import StockPicker, register_picker

    @register_picker
    class MyPicker(StockPicker):
        name = "my_picker"
        label = "My Picker"
        def evaluate(self, snap): ...

Nothing else needs to change — the scanner engine and the UI discover it
through the registry.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Type

from ..models import ScannerResult, StockSnapshot

PICKER_REGISTRY: dict[str, "StockPicker"] = {}


class StockPicker(ABC):
    name: str = "base"
    label: str = "Base Picker"
    description: str = ""

    @abstractmethod
    def evaluate(self, snap: StockSnapshot) -> Optional[ScannerResult]:
        """Return a graded result if the stock is worth watching, else None."""


def register_picker(cls: Type[StockPicker]) -> Type[StockPicker]:
    PICKER_REGISTRY[cls.name] = cls()
    return cls
