"""Indicators computed without lookahead or intermediate rounding."""
from math import isfinite, sqrt

def calculate(closes: list[float], boll_k: float = 2.0):
    if len(closes) < 20:
        return None
    if not all(isfinite(x) and x > 0 for x in closes):
        raise ValueError("Non-positive or nonfinite close")
    window = closes[-20:]
    ma = sum(window) / 20
    sd = sqrt(sum((x - ma) ** 2 for x in window) / 20)
    changes = [b - a for a,b in zip(closes, closes[1:])]
    gain = sum(max(x, 0) for x in changes[:14]) / 14
    loss = sum(max(-x, 0) for x in changes[:14]) / 14
    for delta in changes[14:]:
        gain = (gain*13 + max(delta, 0)) / 14
        loss = (loss*13 + max(-delta, 0)) / 14
    rsi = 50.0 if gain == loss == 0 else (100.0 if loss == 0 else 0.0 if gain == 0 else 100 - 100/(1+gain/loss))
    return {"rsi14": rsi, "ma20": ma, "boll_upper": ma+boll_k*sd, "boll_lower": ma-boll_k*sd}
