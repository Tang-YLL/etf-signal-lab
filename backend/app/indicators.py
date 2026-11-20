from math import sqrt

def calculate(closes: list[float], boll_k: float = 2.0):
    """Wilder RSI14, SMA20 and population-std BOLL20."""
    if len(closes) < 20:
        return None
    if any(p <= 0 for p in closes):
        raise ValueError("Prices must be positive")
    window = closes[-20:]
    ma = sum(window) / 20
    std = sqrt(sum((p - ma) ** 2 for p in window) / 20)
    changes = [b - a for a, b in zip(closes, closes[1:])]
    gain = sum(max(d, 0) for d in changes[:14]) / 14
    loss = sum(max(-d, 0) for d in changes[:14]) / 14
    for d in changes[14:]:
        gain = (gain * 13 + max(d, 0)) / 14
        loss = (loss * 13 + max(-d, 0)) / 14
    rsi = 50.0 if gain == loss == 0 else 100.0 if loss == 0 else 0.0 if gain == 0 else 100 - 100 / (1 + gain / loss)
    return {"rsi14": rsi, "ma20": ma, "boll_upper": ma + boll_k * std, "boll_lower": ma - boll_k * std}
