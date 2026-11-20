from math import sqrt
from app.indicators import calculate
from app.strategies import STRATEGIES, evaluate

def test_constant():
    result=calculate([5.0]*20)
    assert result["ma20"]==result["boll_lower"]==result["boll_upper"]==5.0
    assert result["rsi14"]==50

def test_linear_and_std():
    x=calculate([float(n) for n in range(1,21)])
    assert x["ma20"]==10.5
    assert abs((x["boll_upper"]-10.5)/2-sqrt(33.25))<1e-10

def test_rsi_edges():
    assert calculate([float(x) for x in range(1,21)])["rsi14"]==100
    assert calculate([float(x) for x in range(20,0,-1)])["rsi14"]==0
    assert calculate([1.0]*19) is None

def test_no_lookahead():
    data=[1+n/500 for n in range(100)]
    before = calculate(data[:40])
    data.append(999.0)
    assert calculate(data[:40]) == before  # Historical snapshot uses only prior closes.


def test_signals():
    rule=STRATEGIES["broad"]
    for close,rsi,signal in [(9,39,"B1"),(7.9,29,"B2"),(7.83,24,"B3"),(7.84,25,"B2"),(11,61,"S1"),(12,71,"S2"),(12.25,76,"S3"),(12.24,75,"S2")]:
        assert evaluate(close,{"rsi14":rsi,"ma20":10,"boll_lower":8,"boll_upper":12},rule)==signal
