# Refactor & optimization report

Measured on 2026-10-31 with `pytest --cov`, `ruff`, `radon cc`.

| Metric | Before | After |
|---|---|---|
| Tests | 26 passed | 26 passed |
| Coverage | 87% (no gate) | 87% (CI now fails under 60%) |
| Lint issues (ruff, extended rule set) | 22 | 0 (3 broad `except` lines kept on purpose and marked `noqa`) |
| Average cyclomatic complexity | A (3.3) | A (3.3), no change |
| Most complex functions | `ingest_dataframe` 16, `dashboard` 16, `monthly_report` 12 | unchanged |
| Scoring 6,370 customers | 2.04 s (first run) | 2–4 s (varies by machine) |

What changed: timezone-aware `datetime.now(UTC)` in exports, unused variable removed, long SQL string wrapped, safe-import fixes via `ruff --fix`, CI runs lint and coverage.

Honest limits: no performance work was done beyond vectorised batch scoring (one model call for all customers instead of one per customer, which is where the seconds come from). The three functions with complexity above 10 are the next refactor candidates; they were not refactored.
