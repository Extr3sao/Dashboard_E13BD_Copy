# Backend test performance profile

## Environment

- Source: `756a004` plus current uncommitted hardening and lint fixes.
- Interpreter: `C:\dev\dashboard-e13bd-cert\.venv\Scripts\python.exe` (Python 3.14.3).
- Filesystem: local NTFS checkout; no OneDrive interpreter or site-packages path.

## Measured distribution suite

`python -m pytest -q tests/test_automation.py --durations=20` completed: **44 passed in 120.86s**.

| Test | Call duration | Classification | Evidence-based cause |
|---|---:|---|---|
| `test_distribution_summary_email_merges_tic_summary_and_tic_route_recipients` | 9.47s | EXPECTED_EXPENSIVE_TEST | PDF/distribution pipeline and artifact generation. |
| `test_execute_distribution_job_can_override_all_recipients_for_testing` | 9.06s | EXPECTED_EXPENSIVE_TEST | Real report/distribution artifact path under mocked delivery. |
| `test_distribution_email_uses_catalan_summary_and_technical_legend` | 7.20s | EXPECTED_EXPENSIVE_TEST | Report construction plus delivery composition. |
| `test_execute_distribution_job_test_mode_without_explicit_targets_simulates_all_audiences` | 6.30s | EXPECTED_EXPENSIVE_TEST | Multi-audience artifact work. |
| `test_execute_distribution_job_builds_zip_and_sends_split_emails` | 6.29s | EXPECTED_EXPENSIVE_TEST | ZIP/PDF generation plus split-delivery assertions. |

The slow path is not a hang: all 44 tests completed, and the top calls correlate with deliberately real PDF/ZIP artifact construction. No optimization was applied because no redundant work or resource leak has yet been demonstrated; replacing these with empty mocks would reduce meaningful integration coverage.

## Follow-up

The full suite must retain duration profiling. Candidate DEV Agent enhancement: record environment provenance, distinguish observable-progress slow tests from hung tests, and retain artifact-residue before/after snapshots.

## Full canonical baseline

`python -m pytest -q --durations=20` completed **251 passed in 244.13s**. The slowest test was the real PDF bundle integration at 15.02s; the next distribution/report tests ranged from 3.55s to 13.23s. This confirms `SLOW_TEST` / `EXPECTED_EXPENSIVE_TEST`, not `SUSPECTED_HANG`: the process emitted regular progress, exited 0, and preserved meaningful rendering coverage.
