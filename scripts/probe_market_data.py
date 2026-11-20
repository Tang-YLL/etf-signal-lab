"""One-off external market-data probe. Uses no bypass and redistributes no bars."""
import json
import multiprocessing
import os
from datetime import date, datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

def worker(task, queue):
    try:
        from app.provider import AKShareProvider
        provider = AKShareProvider()
        if task.startswith("history"):
            code = "510300" if task == "history_sh" else "159915"
            bars = provider.get_daily_bars(code, date(2026, 10, 1), date(2026, 11, 19), "RAW")
            value = {"rows": len(bars), "first_date": bars[0].date, "last_date": bars[-1].date, "symbol": code}
        elif task == "spot_search":
            records = provider.get_instruments("510300")
            value = {"matches": len(records), "matched_510300": any(x["symbol"] == "510300" for x in records)}
            if not value["matched_510300"]:
                raise RuntimeError("Search did not return requested ETF")
        elif task == "spot_sina":
            import akshare
            df=akshare.fund_etf_category_sina(symbol="ETF基金")
            if df is None or df.empty or not {"代码","名称"}.issubset(df.columns):
                raise RuntimeError("Sina ETF list returned empty or unexpected schema")
            examples=[str(x) for x in df["代码"].head(3)]
            value={"rows":len(df),"code_examples":examples,"has_510300":any("510300" in str(x) for x in df["代码"])}
        elif task == "calendar":
            dates = provider.get_trading_calendar()
            value = {"dates": len(dates), "recent_date": dates[-1] if dates else None}
            if not dates:
                raise RuntimeError("Empty trading calendar")
        else:
            raise RuntimeError("Unknown probe")
        queue.put({"status": "PASS", "detail": value})
    except Exception as exc:
        queue.put({"status": "FAIL", "error_type": type(exc).__name__, "message": str(exc)[:240]})

def probe(task: str, timeout: int = 35):
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=worker, args=(task,queue))
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.terminate()
        process.join(5)
        result = {"status": "TIMEOUT", "limit_seconds": timeout}
    elif not queue.empty():
        result = queue.get_nowait()
    else:
        result = {"status": "FAIL", "error_type": "ProcessExited", "exit_code": process.exitcode}
    queue.close()
    return result

def main():
    try:
        import akshare
        version = getattr(akshare, "__version__", "unknown")
    except Exception as exc:
        version = f"unavailable: {type(exc).__name__}"
    findings = {task: probe(task) for task in ("history_sh","history_sz","spot_search","spot_sina","calendar")}
    report = {
        "probed_at_utc": datetime.now(timezone.utc).isoformat(),
        "akshare_version": version,
        "history_adjustment": "RAW",
        "external_source": "Eastmoney via AKShare; Sina trading calendar",
        "results": findings,
        "disclaimer": "A passing probe proves only point-in-time network/schema access, not reliability or final data verification. No market data is redistributed."
    }
    Path("data-source-probe.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        rows = [f"| {key} | {value['status']} | {value.get('message','')} |" for key,value in findings.items()]
        with open(summary,"a",encoding="utf-8") as output:
            output.write("## AKShare live source verification\n\n"
                         f"Version: `{version}` | UTC: {report['probed_at_utc']}\n\n"
                         "| Probe | Result | Details |\n|---|---|---|\n"
                         + "\n".join(rows) + "\n\nStatus does not certify vendor finality or usage rights.\n")

if __name__ == "__main__":
    main()
