"""Application configuration.

Values here mirror the trading plan in the Warrior Trading Small Account Tool Kit:
risk ~5% of account per trade, 2:1 profit-to-loss ratio, daily max loss 10%,
halt after 3 consecutive losers, trading window 7:00-11:00 ET.
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel


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
    host: str = "127.0.0.1"
    # probed in order when no explicit port is given: TWS paper, Gateway paper
    paper_ports: list[int] = [7497, 4002]
    # TWS live, Gateway live — connections to these are FORCED read-only;
    # there is no runtime path that places orders on a live account.
    live_ports: list[int] = [7496, 4001]
    client_id: int = 7


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
