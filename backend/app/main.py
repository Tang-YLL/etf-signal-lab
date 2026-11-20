from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from .indicators import calculate
from .strategies import STRATEGIES, evaluate

app = FastAPI(title="ETF Signal Lab", version="0.1.0")

class AnalysisRequest(BaseModel):
    closes: list[float] = Field(min_length=20)
    category: str = "broad"

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "stage": "scaffold"}

@app.post("/api/v1/analyze")
def analyze(body: AnalysisRequest):
    strategy = STRATEGIES.get(body.category)
    if strategy is None: raise HTTPException(400, "Unknown category")
    try:
        result = calculate(body.closes, strategy.boll_k)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"indicators": result, "signal": evaluate(body.closes[-1], result, strategy), "data_status": "USER_SUPPLIED"}
