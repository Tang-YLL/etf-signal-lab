# Next-day conditional close thresholds

The solver appends one hypothetical next-session close to a known close series. It recomputes Wilder RSI14, MA20 and BOLL20 including that hypothetical close. Each six-level condition is evaluated independently at every price tick within a caller-provided **bounded** range.

- Status `BOUNDED_EXHAUSTIVE` means every valid tick inside the specified range was checked, **not** that the full positive-price domain was solved.
- `RANGE_TOO_LARGE` rejects more than 50,000 candidate ticks by default.
- `INVALID_HISTORY` and `INVALID_RANGE` reject unsuitable inputs.
- Each returned interval contains inclusive first and last matching ticks. Strict inequalities in strategy conditions are applied before tick discretization.
- A weaker level can overlap a stronger one; the ordinary current-signal engine chooses the strongest. The solver reports each condition's matching regions independently.
- These are theoretical conditional closes, not predictions or verified executable prices. Corporate actions and adjusted-price conversions are not yet implemented.
