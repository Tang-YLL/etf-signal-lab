from dataclasses import dataclass

@dataclass(frozen=True)
class Strategy:
    buy_rsi: tuple[int, int, int]
    sell_rsi: tuple[int, int, int]
    boll_k: float
    extreme_deviation: float
    enabled: bool = True

STRATEGIES = {
    "broad": Strategy((40, 30, 25), (60, 70, 75), 2.0, .02),
    "dividend_low_vol": Strategy((42, 32, 27), (58, 68, 73), 2.0, .015),
    "sector": Strategy((38, 28, 23), (62, 72, 77), 2.2, .03),
    "cross_border": Strategy((38, 28, 23), (62, 72, 77), 2.2, .03),
    "bond": Strategy((45, 35, 30), (55, 65, 70), 1.8, .005, False),
    "gold": Strategy((40, 30, 25), (60, 70, 75), 2.2, .025),
}

def evaluate(price: float, indicators: dict | None, strategy: Strategy):
    if indicators is None: return "UNAVAILABLE"
    if not strategy.enabled: return "WATCH"
    r, m = indicators["rsi14"], indicators["ma20"]
    l, u = indicators["boll_lower"], indicators["boll_upper"]
    buys = [r <= strategy.buy_rsi[0] and price <= m,
            r <= strategy.buy_rsi[1] and price <= l,
            r <= strategy.buy_rsi[2] and l > 0 and price < l * (1 - strategy.extreme_deviation)]
    sells = [r >= strategy.sell_rsi[0] and price >= m,
             r >= strategy.sell_rsi[1] and price >= u,
             r >= strategy.sell_rsi[2] and price > u * (1 + strategy.extreme_deviation)]
    if any(buys) and any(sells): return "CONFLICT"
    if any(buys): return "B" + str(max(i + 1 for i, v in enumerate(buys) if v))
    if any(sells): return "S" + str(max(i + 1 for i, v in enumerate(sells) if v))
    return "WATCH"
