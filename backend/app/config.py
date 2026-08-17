"""Application configuration.

Values here mirror the trading plan in the Warrior Trading Small Account Tool Kit:
risk ~5% of account per trade, 2:1 profit-to-loss ratio, daily max loss 10%,
halt after 3 consecutive losers, trading window 7:00-11:00 ET.
"""
from __future__ import annotations

from enum import Enum
import os
from pydantic import BaseModel


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Mode(str, Enum):
    SIM = "sim"        # synthetic market + paper broker (no dependencies)
    PAPER = "paper"    # IBKR market data + IBKR paper account (port 7497)
    LIVE = "live"      # real money (port 7496); requires explicit opt-in


class RiskConfig(BaseModel):
    account_risk_pct: float = 0.05        # risk per trade as fraction of equity
    profit_loss_ratio: float = 2.0        # target = ratio * stop distance
    daily_max_loss_pct: float = 0.10      # halt for the day beyond this
    max_consecutive_losers: int = 3       # halt after N consecutive losing trades
    trading_start_et: str = "07:00"
    trading_end_et: str = "11:00"
    max_position_pct: float = 1.0         # max notional as fraction of equity


class IBKRConfig(BaseModel):
    host: str = os.getenv("STOCKTRADE_IBKR_HOST", "127.0.0.1")
    # Probe Gateway first, then TWS.
    paper_ports: list[int] = [
        int(port.strip())
        for port in os.getenv("STOCKTRADE_IBKR_PAPER_PORTS", "4002,7497").split(",")
        if port.strip()
    ]
    # TWS live, Gateway live. Orders require the separate live-trading opt-in
    # and runtime unlock; otherwise these ports remain read-only.
    live_ports: list[int] = [
        int(port.strip())
        for port in os.getenv("STOCKTRADE_IBKR_LIVE_PORTS", "4001,7496").split(",")
        if port.strip()
    ]
    client_id: int = int(os.getenv("STOCKTRADE_IBKR_CLIENT_ID", "7"))
    live_trading_enabled: bool = _env_flag("STOCKTRADE_ENABLE_LIVE_TRADING")


class Settings(BaseModel):
    mode: Mode = Mode.SIM
    starting_equity: float = 5_000.0
    default_share_size: int = 100
    market_condition: str = "hot"         # "hot" | "cold" — affects float threshold
    risk: RiskConfig = RiskConfig()
    ibkr: IBKRConfig = IBKRConfig()
    active_picker: str = "ross_cameron"
    active_strategy: str = "macd_cross"


settings = Settings()
