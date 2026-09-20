# Design

## Current-state evidence

The framework source authority declares DEV Agent 4.5.1 / `REL-4.5.1-E6116BDBD69B`, but its worktree is dirty and its release approval is pending. The Dashboard's existing verifier documents an open framework false-success vector and therefore `NOT_CERTIFIED`.

## Change

Add one Windows GitHub Actions workflow using the repository's own commands: Python dependency installation and `pytest -q`; Node `npm ci`, lint, Vitest, Vite build, and mocked Playwright smoke. It neither accesses Oracle nor reads secrets.

Add reports that make the certification boundary explicit and give a scored, testable roadmap. No data, API success contract, or framework source is changed.

The narrowly scoped runtime hardening replaces raw exception responses in the shared internal-error wrapper and Oracle connection-test endpoint with stable Catalan user messages. Existing server-side exception logging remains the diagnostic authority; no API shape or successful response changes.

## Security and failure handling

The workflow uses no repository secrets and does not upload artifacts containing configuration or data. Missing Playwright browser dependencies fail visibly. Oracle integration is intentionally outside the workflow.

## Validation strategy

AC-001/002 are checked by file/content inspection. AC-003 is checked by workflow review and local command execution where the declared tools are available. AC-004 is recorded in `verification.md`.
AC-005 is checked by `tests/test_main_runtime.py`, including a secret-shaped exception fixture.
