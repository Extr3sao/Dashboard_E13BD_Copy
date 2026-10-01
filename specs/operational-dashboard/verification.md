# Verification

`audit_runs` records a compact, redacted result ledger after each reconciliation. Fleet status is derived server-side from the newest execution, full/partial coverage, staleness, active findings and Red Flags. It never treats zero findings as healthy without successful full coverage.

Evidence: `tests/test_operational_dashboard.py` verifies healthy, critical, failed and degraded targets plus stale data/trends. `python -m pytest -q` passed with 281 tests. `npm test` passed with 80 tests; lint and production build passed. The dashboard uses one fleet aggregation request and fetches a target detail only on selection, avoiding obvious N+1 traffic.
