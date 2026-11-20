# Data sources and verification

Primary adapter: AKShare `fund_etf_hist_em` and `fund_etf_spot_em`. The provider supplies daily OHLCV only in RAW (unadjusted) mode. The calendar uses `tool_trade_date_hist_sina`.

## Reliability boundaries

The upstream source can return connection errors, empty responses, malformed fields or revisions. See the separate **Market source probe (non-blocking)** Actions workflow, which probes two ETF codes, catalogue search and calendar in bounded child processes. Its JSON artifact is a point-in-time check, not guaranteed access and **not a substitute for user deployment tests**.

The project does **not** bypass bot checks, rate limits or access controls. The AKShare open-source license does not establish redistribution or commercial-use rights over market data from upstream providers.

The backend market refresh continues to keep prior SQLite data if a request fails, displays a failure reason and does not upgrade a new sample to CONFIRMED until a second identical sample at least 10 minutes later after the 18:00 trading-day cutoff. This is a heuristic stability test, not exchange or vendor finality.

The quoted ETF examples are verification identifiers, not trading recommendations.

## Verified network probe snapshots (2026-11-20)

- [First run](https://github.com/Tang-YLL/etf-signal-lab/actions/runs/44729556425) — AKShare 1.20.65; RAW history for 510300 and 159915 succeeded (31 daily rows each); Eastmoney ETF catalogue returned HTTP 502; old calendar name was removed.
- [Second run](https://github.com/Tang-YLL/etf-signal-lab/actions/runs/44730040112) — Eastmoney daily history returned Push2RateLimitError for both samples, Eastmoney catalogue still HTTP 502. Sina ETF catalogue succeeded (927 rows including 510300) and renamed Sina calendar succeeded (8,797 dates).
- Provider search now **prefers Eastmoney catalogue, fails over to the verified Sina list** and caches it in-memory to reduce repeated requests. After Eastmoney errors, it waits at least 30 minutes before another Eastmoney catalogue attempt. When both fail, existing cache is marked STALE_CATALOGUE.
- These are environment and moment-specific outcomes, **not** a claim of permanent reliability. The Sina catalogue may omit newly issued funds; manually entered ETF identities still require verification.
