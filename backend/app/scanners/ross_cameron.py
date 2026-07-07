"""Ross Cameron's stock selection criteria (Warrior Trading Small Account Tool Kit).

The five criteria:
  1. Relative volume >= 5x the 30-day average
  2. Already up >= 10% on the day
  3. News catalyst preferred (headline justifying the move)
  4. Price between $1.00 and $20.00 (sweet spot $5-$10 for small accounts)
  5. Float under 20M shares in a hot market, under 10M in a cold market

A stock meeting all five is A-quality. Grading below: A = all pass,
B = the four hard criteria pass but no catalyst, C = one hard miss but
close enough to keep on watch.
"""
from __future__ import annotations

import time
from typing import Optional

from ..config import settings
from ..models import CriterionCheck, ScannerResult, StockSnapshot
from .base import StockPicker, register_picker

MIN_PRICE = 1.00
MAX_PRICE = 20.00
SWEET_LOW = 5.00
SWEET_HIGH = 10.00
MIN_REL_VOL = 5.0
MIN_CHANGE_PCT = 10.0
FLOAT_HOT = 20_000_000
FLOAT_COLD = 10_000_000


def _fmt_float(shares: Optional[int]) -> str:
    if shares is None:
        return "unknown"
    return f"{shares / 1_000_000:.1f}M"


@register_picker
class RossCameronPicker(StockPicker):
    name = "ross_cameron"
    label = "Ross Cameron — Small Cap Momentum"
    description = (
        "5x relative volume, up 10%+ on the day, $1-$20 price band "
        "($5-$10 sweet spot), float under 20M (hot) / 10M (cold), "
        "news catalyst preferred."
    )

    def evaluate(self, snap: StockSnapshot) -> Optional[ScannerResult]:
        float_cap = FLOAT_HOT if settings.market_condition == "hot" else FLOAT_COLD

        rel_vol = snap.relative_volume
        change = snap.change_pct

        checks = [
            CriterionCheck(
                name="Relative volume ≥ 5x",
                passed=rel_vol >= MIN_REL_VOL,
                value=f"{rel_vol:.1f}x",
            ),
            CriterionCheck(
                name="Up ≥ 10% today",
                passed=change >= MIN_CHANGE_PCT,
                value=f"{change:+.1f}%",
            ),
            CriterionCheck(
                name="Price $1–$20",
                passed=MIN_PRICE <= snap.price <= MAX_PRICE,
                value=f"${snap.price:.2f}",
                detail="in $5–$10 sweet spot"
                if SWEET_LOW <= snap.price <= SWEET_HIGH
                else "",
            ),
            CriterionCheck(
                name=f"Float < {float_cap // 1_000_000}M ({settings.market_condition})",
                # Unknown float (common without a fundamentals subscription)
                # passes softly rather than sinking an otherwise-good stock.
                passed=snap.float_shares is None or snap.float_shares < float_cap,
                value=_fmt_float(snap.float_shares),
                detail="float unknown — verify manually" if snap.float_shares is None else "",
            ),
            CriterionCheck(
                name="News catalyst",
                passed=snap.has_news,
                value=(snap.headline[:60] + "…")
                if snap.headline and len(snap.headline) > 60
                else (snap.headline or "none"),
            ),
        ]

        hard = checks[:4]           # catalyst is a preference, not a hard filter
        hard_passes = sum(c.passed for c in hard)

        if hard_passes == 4:
            grade = "A" if snap.has_news else "B"
        elif hard_passes == 3:
            grade = "C"
        else:
            return None

        # Ranking score: weight the demand-side magnitudes, bonus for sweet
        # spot and catalyst, penalty for thicker floats.
        score = 0.0
        score += min(rel_vol / MIN_REL_VOL, 10) * 10          # up to 100 → scaled
        score += min(change / MIN_CHANGE_PCT, 5) * 8
        if SWEET_LOW <= snap.price <= SWEET_HIGH:
            score += 15
        if snap.float_shares:
            score += max(0.0, (float_cap - snap.float_shares) / float_cap) * 15
        if snap.has_news:
            score += 20
        score = round(min(score, 100.0), 1)

        return ScannerResult(
            symbol=snap.symbol,
            picker=self.name,
            grade=grade,
            score=score,
            price=snap.price,
            change_pct=round(change, 2),
            relative_volume=round(rel_vol, 2),
            float_shares=snap.float_shares,
            headline=snap.headline,
            checks=checks,
            ts=time.time(),
        )
