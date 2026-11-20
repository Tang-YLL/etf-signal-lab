"""Bounded exhaustive next-close scenario solver; not a price forecast."""
from decimal import Decimal, InvalidOperation
from math import isfinite, sqrt

LEVELS = ("B1", "B2", "B3", "S1", "S2", "S3")

def solve(closes, strategy, minimum: str, maximum: str, tick: str = "0.001", max_ticks: int = 50000):
    if len(closes) < 20 or any(not isfinite(x) or x <= 0 for x in closes):
        return {"status": "INVALID_HISTORY", "intervals": {}}
    try:
        low, high, step = Decimal(minimum), Decimal(maximum), Decimal(tick)
        if not all(x.is_finite() for x in (low, high, step)) or low <= 0 or high < low or step <= 0:
            raise ValueError("invalid range")
        first, last = low / step, high / step
        if first != first.to_integral_value() or last != last.to_integral_value():
            raise ValueError("unaligned tick")
        first, last = int(first), int(last)
        if last - first + 1 > max_ticks:
            return {"status": "RANGE_TOO_LARGE", "intervals": {}, "max_ticks": max_ticks}
    except (ValueError, InvalidOperation, ArithmeticError):
        return {"status": "INVALID_RANGE", "intervals": {}}

    changes = [b-a for a,b in zip(closes, closes[1:])]
    gain = sum(max(x, 0) for x in changes[:14]) / 14
    loss = sum(max(-x, 0) for x in changes[:14]) / 14
    for x in changes[14:]:
        gain = (gain*13 + max(x, 0)) / 14
        loss = (loss*13 + max(-x, 0)) / 14
    window = closes[-19:]
    total, squares, previous = sum(window), sum(x*x for x in window), closes[-1]
    intervals = {level: [] for level in LEVELS}
    opened = {level: None for level in LEVELS}
    for index in range(first, last+2):
        if index <= last:
            price = float(step*index)
            change = price-previous
            g = (gain*13+max(change,0))/14
            l = (loss*13+max(-change,0))/14
            rsi = 50 if g == l == 0 else 100 if l == 0 else 0 if g == 0 else 100-100/(1+g/l)
            ma = (total+price)/20
            sd = sqrt(max(0,(squares+price*price)/20-ma*ma))
            lower, upper = ma-strategy.boll_k*sd, ma+strategy.boll_k*sd
            flags = (
                rsi <= strategy.buy_rsi[0] and price <= ma,
                rsi <= strategy.buy_rsi[1] and price <= lower,
                rsi <= strategy.buy_rsi[2] and lower > 0 and price < lower*(1-strategy.extreme_deviation),
                rsi >= strategy.sell_rsi[0] and price >= ma,
                rsi >= strategy.sell_rsi[1] and price >= upper,
                rsi >= strategy.sell_rsi[2] and price > upper*(1+strategy.extreme_deviation)
            ) if strategy.enabled else (False,)*6
        else:
            flags = (False,)*6
        for level, matched in zip(LEVELS, flags):
            if matched and opened[level] is None:
                opened[level] = index
            if not matched and opened[level] is not None:
                start = opened[level]
                intervals[level].append({
                    "from": str(step*start), "to": str(step*(index-1)),
                    "from_inclusive": True, "to_inclusive": True,
                    "change_pct_at_from": round((float(step*start)/previous-1)*100,4)
                })
                opened[level] = None
    return {
        "status": "BOUNDED_EXHAUSTIVE",
        "intervals": intervals,
        "range": {"minimum": str(low), "maximum": str(high), "tick": str(step)},
        "limitations": [
            "Only specified price range searched",
            "Conditional close scenarios, not forecasts",
            "Corporate actions and adjusted-to-raw conversion unverified"
        ]
    }
