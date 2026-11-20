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
