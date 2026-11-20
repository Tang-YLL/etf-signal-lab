from math import sqrt
from app.indicators import calculate
from app.strategies import STRATEGIES, evaluate

def test_flat():
    result = calculate([5.0] * 20)
    assert result["rsi14"] == 50
    assert result["ma20"] == result["boll_upper"] == result["boll_lower"] == 5

def test_population_std():
    result = calculate(list(range(1, 21)))
    assert result["ma20"] == 10.5
    assert abs((result["boll_upper"] - 10.5) / 2 - sqrt(33.25)) < 1e-10

def test_rsi_extremes():
    assert calculate(list(range(1, 21)))["rsi14"] == 100
    assert calculate(list(range(20, 0, -1)))["rsi14"] == 0

def test_signals():
    r = STRATEGIES["broad"]
    for price, rsi, expected in [(9,39,"B1"), (7.9,29,"B2"), (7.83,24,"B3"), (7.84,25,"B2"), (11,61,"S1"), (12,71,"S2"), (12.25,76,"S3"), (12.24,75,"S2")]:
        indicators = {"rsi14":rsi,"ma20":10,"boll_lower":8,"boll_upper":12}
        assert evaluate(price, indicators, r) == expected
