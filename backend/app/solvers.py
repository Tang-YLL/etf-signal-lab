"""Exact inspection of price ticks within a stated finite domain, no monotonicity assumption."""
from decimal import Decimal, InvalidOperation
from math import sqrt, isfinite

LEVELS = ("B1", "B2", "B3", "S1", "S2", "S3")

def solve(closes, strategy, minimum: str | None = None, maximum: str | None = None, tick: str = "0.001", max_ticks: int = 50000):
    if len(closes) < 20 or any(not isfinite(x) or x <= 0 for x in closes):
        return {"status": "INVALID_HISTORY", "intervals": {}}
    try:
        step = Decimal(tick)
        if step <= 0 or not step.is_finite(): raise ValueError("tick")
        previous = Decimal(str(closes[-1]))
        low = Decimal(minimum) if minimum is not None else previous * Decimal("0.70")
        high = Decimal(maximum) if maximum is not None else previous * Decimal("1.30")
        if not low.is_finite() or not high.is_finite() or high < low or low <= 0: raise ValueError("range")
        first = int((low/step).to_integral_value(rounding="ROUND_CEILING"))
        last = int((high/step).to_integral_value(rounding="ROUND_FLOOR"))
        if first > last: raise ValueError("empty tick range")
        if last-first+1 > max_ticks:
            return {"status": "RANGE_TOO_LARGE", "intervals": {}, "ticks": last-first+1}
    except (InvalidOperation, ValueError, ArithmeticError):
        return {"status": "INVALID_RANGE", "intervals": {}}
    changes = [b-a for a,b in zip(closes, closes[1:])]
    gain = sum(max(x, 0) for x in changes[:14]) / 14
    loss = sum(max(-x, 0) for x in changes[:14]) / 14
    for x in changes[14:]:
        gain = (gain*13+max(x,0))/14
        loss = (loss*13+max(-x,0))/14
    window = closes[-19:]
    total, square, prev = sum(window), sum(x*x for x in window), closes[-1]
    intervals = {level: [] for level in LEVELS}
    opened = {level: None for level in LEVELS}
    for index in range(first, last+2):
        flags = (False,)*6
        if index <= last and strategy.enabled:
            p = float(step*index)
            delta = p-prev
            g, l = (gain*13+max(delta,0))/14, (loss*13+max(-delta,0))/14
            rsi = 50 if g == l == 0 else 100 if l == 0 else 0 if g == 0 else 100-100/(1+g/l)
            ma = (total+p)/20
            sd = sqrt(max(0, (square+p*p)/20-ma*ma))
            lower, upper = ma-strategy.boll_k*sd, ma+strategy.boll_k*sd
            flags = (rsi <= strategy.buy_rsi[0] and p <= ma,
                     rsi <= strategy.buy_rsi[1] and p <= lower,
                     rsi <= strategy.buy_rsi[2] and lower > 0 and p < lower*(1-strategy.extreme_deviation),
                     rsi >= strategy.sell_rsi[0] and p >= ma,
                     rsi >= strategy.sell_rsi[1] and p >= upper,
                     rsi >= strategy.sell_rsi[2] and p > upper*(1+strategy.extreme_deviation))
        for level, matched in zip(LEVELS, flags):
            if matched and opened[level] is None: opened[level] = index
            if not matched and opened[level] is not None:
                a,b=step*opened[level],step*(index-1)
                nearest=b if level.startswith("B") else a
                intervals[level].append({"from":str(a),"to":str(b),"inclusive":True,
                    "nearest":str(nearest), "change_pct":round((float(nearest)/prev-1)*100,4)})
                opened[level] = None
    return {"status":"BOUNDED_EXHAUSTIVE","intervals":intervals,"tick":str(step),
            "searched_range":[str(step*first),str(step*last)],
            "price_basis":"RAW_THEORETICAL", "limit":"No completeness claim outside searched range; corporate actions may invalidate observation prices"}
