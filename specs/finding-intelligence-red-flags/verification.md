# Verification

## Architecture and operator workflow

`FindingStore` persists a stable SHA-256 identity formed only from target, rule and normalized object identity. It appends each observation to `finding_occurrences`, while `findings` maintains the current projection. Successful `PASS`, `WARN` and `FAIL` rule scopes may reconcile a missing finding as resolved; `ERROR`, `SKIPPED`, failed execution and omitted scope never do.

Red Flags are deduplicated by stable type/finding or type/target keys. Priority is deterministic from target environment/criticality, finding severity, evolution and persistence. Their stored explanations contain only redacted operational context. The browser-only `/api/findings` router requires a USER session and CSRF for lifecycle mutations. The Problems view provides Needs Attention, detail/history, and acknowledge, accepted-risk, and false-positive actions.

Authentication policy is snapshotted at application construction, rather than consulting the mutable process environment per request. Rejections log the safe `auth_reason` field without headers, cookies, tokens, or credentials.

## Evidence

| Acceptance criterion | Evidence |
| --- | --- |
| AC-001 lifecycle and false-resolution protection | `tests/test_finding_engine.py` covers fingerprint stability, 82→88→94, outage, improving, resolution and reopening. |
| AC-002 history, actions, target context and flags | `tests/test_finding_engine.py` covers append-only history, retained accepted risk, deduplication, priority and execution-health flags. |
| AC-003 API protection and redaction | `tests/test_findings_router.py` verifies 401 anonymous, 403 missing CSRF and successful USER action; normalized engine redaction is reused. |
| AC-004 observable UI | `src/web-app/src/views/FindingsView.test.jsx` verifies priority queue and detail/action workflow. |
| Auth isolation and diagnostics | `tests/test_main_runtime.py` verifies the snapshotted policy and safe structured rejection diagnostic. |

Commands executed:

- `python -m pytest -q` — 278 passed, 0 failed.
- `npm run lint`, `npm test`, `npm run build` — passing before the auth isolation change; the frontend is unaffected by the backend-only policy snapshot.
