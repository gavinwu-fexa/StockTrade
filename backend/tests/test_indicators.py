from app.indicators import EMA, MACD, SMA, Crossover


def test_sma_basic():
    sma = SMA(3)
    assert sma.update(1) is None
    assert sma.update(2) is None
    assert sma.update(3) == 2.0
    assert sma.update(4) == 3.0


def test_ema_seeds_with_sma_then_smooths():
    ema = EMA(3)
    assert ema.update(2) is None
    assert ema.update(4) is None
    assert ema.update(6) == 4.0          # SMA seed
    v = ema.update(8)
    assert v == 4.0 + (8 - 4.0) * 0.5    # multiplier = 2/(3+1)


def test_macd_directions():
    macd = MACD(3, 6, 3)
    for p in range(1, 30):
        macd.update(float(p))
    # steadily rising series → positive MACD
    assert macd.macd is not None and macd.macd > 0
    for p in range(30, 1, -1):
        macd.update(float(p))
    assert macd.macd is not None and macd.macd < 0


def test_crossover_detection():
    c = Crossover()
    assert c.update(1.0, 2.0) is None       # below, first sample
    assert c.update(3.0, 2.0) == "golden"
    assert c.update(4.0, 2.0) is None       # still above
    assert c.update(1.0, 2.0) == "death"


def test_crossover_handles_none():
    c = Crossover()
    assert c.update(None, 1.0) is None
    assert c.update(1.0, None) is None
