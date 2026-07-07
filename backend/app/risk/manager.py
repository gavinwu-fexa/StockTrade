"""Central risk gate. Every order — strategy-generated or hotkey — passes
through here before reaching a broker.

Implements the rules from the Small Account Tool Kit trading plan:
  - Risk ~5% of account per trade; shares sized from stop distance
  - 2:1 profit-to-loss ratio for targets
  - Daily max loss of 10% of the account halts trading
  - Three consecutive losing trades halts trading
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..config import RiskConfig
from ..models import AccountState, OrderRequest, OrderSide, TradeRecord


@dataclass
class RiskDecision:
    approved: bool
    qty: int = 0
    reason: str = ""
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    warnings: list[str] = field(default_factory=list)


class RiskManager:
    def __init__(self, config: RiskConfig, starting_equity: float):
        self.config = config
        self.starting_equity = starting_equity
        self.day_realized_pnl = 0.0
        self.consecutive_losers = 0
        self.halted = False
        self.halt_reason: Optional[str] = None

    # -- trade lifecycle ---------------------------------------------------

    def record_trade(self, trade: TradeRecord) -> None:
        self.day_realized_pnl += trade.pnl
        if trade.pnl < 0:
            self.consecutive_losers += 1
        elif trade.pnl > 0:
            self.consecutive_losers = 0
        self._check_halts()

    def reset_day(self) -> None:
        self.day_realized_pnl = 0.0
        self.consecutive_losers = 0
        self.halted = False
        self.halt_reason = None

    def rearm(self) -> None:
        """Manual override after a halt (e.g. next day, or a deliberate choice)."""
        self.halted = False
        self.halt_reason = None

    def _check_halts(self) -> None:
        max_loss = self.starting_equity * self.config.daily_max_loss_pct
        if self.day_realized_pnl <= -max_loss:
            self.halted = True
            self.halt_reason = (
                f"Daily max loss hit: ${self.day_realized_pnl:.2f} "
                f"(limit -${max_loss:.2f})"
            )
        elif self.consecutive_losers >= self.config.max_consecutive_losers:
            self.halted = True
            self.halt_reason = (
                f"{self.consecutive_losers} consecutive losing trades — done for the day"
            )

    # -- sizing & approval ---------------------------------------------------

    def size_position(self, equity: float, entry: float, stop: Optional[float]) -> tuple[int, float, float]:
        """Return (shares, stop, target) using risk-per-trade and 2:1 R/R."""
        risk_dollars = equity * self.config.account_risk_pct
        if stop is None or stop >= entry:
            stop = round(entry * 0.98, 2)  # fallback 2% stop
        per_share_risk = max(entry - stop, 0.01)
        qty = int(risk_dollars / per_share_risk)
        # cap notional at max_position_pct of equity
        max_notional_qty = int(equity * self.config.max_position_pct / entry) if entry > 0 else 0
        qty = max(0, min(qty, max_notional_qty))
        target = round(entry + self.config.profit_loss_ratio * per_share_risk, 2)
        return qty, stop, target

    def approve(
        self,
        req: OrderRequest,
        account: AccountState,
        current_price: float,
        stop_price: Optional[float] = None,
    ) -> RiskDecision:
        if req.side == OrderSide.SELL:
            # Exits are always allowed — never block someone getting out.
            return RiskDecision(approved=True, qty=req.qty, reason="exit allowed")

        if self.halted:
            return RiskDecision(approved=False, reason=f"Trading halted: {self.halt_reason}")

        warnings: list[str] = []
        qty = req.qty
        sized_qty, stop, target = self.size_position(account.equity, current_price, stop_price)

        if qty <= 0:
            qty = sized_qty
        elif sized_qty and qty > sized_qty:
            warnings.append(
                f"Requested {qty} shares exceeds risk-sized {sized_qty}; clamped."
            )
            qty = sized_qty

        notional = qty * current_price
        if notional > account.cash:
            qty = int(account.cash / current_price) if current_price > 0 else 0
            warnings.append(f"Insufficient cash; reduced to {qty} shares.")

        if qty <= 0:
            return RiskDecision(approved=False, reason="Sized to zero shares (insufficient funds or risk budget)")

        return RiskDecision(
            approved=True,
            qty=qty,
            stop_price=stop,
            target_price=target,
            reason="ok",
            warnings=warnings,
        )

    def snapshot(self) -> dict:
        max_loss = self.starting_equity * self.config.daily_max_loss_pct
        return {
            "day_realized_pnl": round(self.day_realized_pnl, 2),
            "daily_max_loss": round(max_loss, 2),
            "consecutive_losers": self.consecutive_losers,
            "max_consecutive_losers": self.config.max_consecutive_losers,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }
