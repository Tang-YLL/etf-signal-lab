from decimal import Decimal
from app.solvers import solve
from app.strategies import STRATEGIES
from app.indicators import calculate

def test_solver_regions_and_tick():
    prices=[1.0]*30
    result=solve(prices,STRATEGIES["broad"],"0.500","1.500","0.001")
    assert result["status"]=="BOUNDED_EXHAUSTIVE"
    assert result["intervals"]["B1"]
    assert result["intervals"]["S1"]
    for regions in result["intervals"].values():
        for r in regions:
            assert float(r["from"])<=float(r["to"])
            assert Decimal(r["from"]) / Decimal("0.001") == (Decimal(r["from"]) / Decimal("0.001")).to_integral_value()

def test_invalid_or_large():
    rule=STRATEGIES["broad"]
    assert solve([1.0]*10,rule)["status"]=="INVALID_HISTORY"
    assert solve([1.0]*30,rule,tick="0")["status"]=="INVALID_RANGE"
    assert solve([1.0]*30,rule,"0.001","200.0")["status"]=="RANGE_TOO_LARGE"

def test_disabled_bond():
    result=solve([1.0]*30,STRATEGIES["bond"])
    assert all(not x for x in result["intervals"].values())

def test_solver_matches_direct_indicators():
    rule=STRATEGIES["broad"]
    p=[1.0+i*.001 for i in range(35)]
    result=solve(p,rule,"0.800","1.200","0.001")
    from app.strategies import evaluate
    for tick in (800,900,1000,1100,1200):
        price=tick/1000
        s=evaluate(price,calculate([*p,price],rule.boll_k),rule)
        if s.startswith(("B","S")):
            assert any(float(r["from"])<=price<=float(r["to"]) for r in result["intervals"][s])

def test_bounded_solver_matches_direct_six_conditions_on_random_histories():
    # Independent oracle: recompute all indicators for every hypothetical tick.
    # Unlike evaluate(), this checks weaker levels even when a stronger level overlaps.
    from random import Random
    for seed in range(16):
        rng=Random(seed)
        prices=[1.0]
        for _ in range(39):
            prices.append(max(.2,prices[-1]+rng.uniform(-.025,.025)))
        rule=STRATEGIES[["broad","dividend_low_vol","sector","cross_border","gold"][seed%5]]
        result=solve(prices,rule,"0.600","1.400","0.005")
        assert result["status"]=="BOUNDED_EXHAUSTIVE"
        for tick in range(120,281):
            p=tick*.005
            i=calculate([*prices,p],rule.boll_k)
            r,ma,lower,upper=(i["rsi14"],i["ma20"],i["boll_lower"],i["boll_upper"])
            expected={
                "B1":r<=rule.buy_rsi[0] and p<=ma,
                "B2":r<=rule.buy_rsi[1] and p<=lower,
                "B3":r<=rule.buy_rsi[2] and lower>0 and p<lower*(1-rule.extreme_deviation),
                "S1":r>=rule.sell_rsi[0] and p>=ma,
                "S2":r>=rule.sell_rsi[1] and p>=upper,
                "S3":r>=rule.sell_rsi[2] and p>upper*(1+rule.extreme_deviation)
            }
            for level,should_match in expected.items():
                actual=any(float(segment["from"])-1e-12<=p<=float(segment["to"])+1e-12
                           for segment in result["intervals"][level])
                assert actual==should_match,(seed,p,level,actual,should_match)
