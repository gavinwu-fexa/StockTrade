from app.models import StockSnapshot
from app.scanners import PICKER_REGISTRY


def make_snap(**kw):
    base = dict(
        symbol="TEST",
        price=6.50,
        prev_close=5.00,
        day_volume=5_000_000,
        avg_volume_30d=400_000,
        float_shares=8_000_000,
        has_news=True,
        headline="TEST announces FDA approval",
    )
    base.update(kw)
    return StockSnapshot(**base)


picker = PICKER_REGISTRY["ross_cameron"]


def test_a_grade_when_all_criteria_met():
    res = picker.evaluate(make_snap())
    assert res is not None
    assert res.grade == "A"
    assert all(c.passed for c in res.checks)


def test_b_grade_without_news():
    res = picker.evaluate(make_snap(has_news=False, headline=None))
    assert res is not None
    assert res.grade == "B"


def test_rejects_expensive_stock():
    res = picker.evaluate(make_snap(price=232.0, prev_close=210.0))
    assert res is None or res.grade == "C"


def test_rejects_low_relative_volume_and_flat():
    res = picker.evaluate(make_snap(
        day_volume=500_000, avg_volume_30d=400_000,  # 1.25x rel vol
        price=5.05, prev_close=5.00,                  # +1%
    ))
    assert res is None


def test_c_grade_with_one_hard_miss():
    res = picker.evaluate(make_snap(float_shares=25_000_000))  # float too big
    assert res is not None
    assert res.grade == "C"


def test_scores_rank_better_stocks_higher():
    strong = picker.evaluate(make_snap(day_volume=20_000_000))
    weak = picker.evaluate(make_snap(day_volume=2_400_000, has_news=False, headline=None))
    assert strong.score > weak.score
