from app.solvers import solve
from app.strategies import STRATEGIES, Strategy

def test_levels_and_ranges():
    result = solve([1.0]*30, STRATEGIES["broad"], "0.500", "1.500")
    assert result["status"] == "BOUNDED_EXHAUSTIVE"
    assert result["intervals"]["B1"]
    assert result["intervals"]["S1"]
    for regions in result["intervals"].values():
        assert all(float(r["from"]) <= float(r["to"]) for r in regions)

def test_invalid_and_large():
    rule = STRATEGIES["broad"]
    assert solve([1.0]*30, rule, "0.1", "1", "0.3")["status"] == "INVALID_RANGE"
    assert solve([1.0]*30, rule, "0.001", "1000", "0.001")["status"] == "RANGE_TOO_LARGE"
    assert solve([1.0]*10, rule, "0.5", "1.5")["status"] == "INVALID_HISTORY"

def test_bond_disabled():
    result = solve([1.0]*30, STRATEGIES["bond"], "0.50", "1.50", "0.01")
    assert all(not x for x in result["intervals"].values())

def test_single_tick():
    result = solve([1.0]*30, STRATEGIES["broad"], "1.000", "1.000")
    assert result["status"] == "BOUNDED_EXHAUSTIVE"
