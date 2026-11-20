# Data sources and verification

Primary adapter: AKShare `fund_etf_hist_em` and `fund_etf_spot_em`. The provider supplies daily OHLCV only in RAW (unadjusted) mode. The calendar uses `tool_trade_date_hist_sina`.

## Reliability boundaries

The upstream source can return connection errors, empty responses, malformed fields or revisions. See the separate **Market source probe (non-blocking)** Actions workflow, which probes two ETF codes, catalogue search and calendar in bounded child processes. Its JSON artifact is a point-in-time check, not guaranteed access and **not a substitute for user deployment tests**.

The project does **not** bypass bot checks, rate limits or access controls. The AKShare open-source license does not establish redistribution or commercial-use rights over market data from upstream providers.

The backend market refresh continues to keep prior SQLite data if a request fails, displays a failure reason and does not upgrade a new sample to CONFIRMED until a second identical sample at least 10 minutes later after the 18:00 trading-day cutoff. This is a heuristic stability test, not exchange or vendor finality.

The quoted ETF examples are verification identifiers, not trading recommendations.
