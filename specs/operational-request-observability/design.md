# Design

## Current-state evidence

`src/api/main.py` creates the FastAPI app and has CORS and frame middleware but no health route or request-correlation middleware. The route inventory contains 97 decorated API endpoints.

## Approach

A `BaseHTTPMiddleware` obtains `X-Request-ID` only when it matches a bounded safe token pattern; otherwise it generates a UUID. It returns that value in the response header and emits one `request_completed` event using logging `extra` fields. It records method and path only, never URL/query/body. Two constant, dependency-free routes describe liveness and local readiness.

The middleware measures duration around `call_next`. If an unexpected exception escapes the route stack, it creates the standard generic JSON 500 inside the middleware so the correlation header and one redacted completion event are not bypassed. Deliberate `HTTPException` responses flow through normally.

## Failure and security handling

Identifier input is constrained to printable token characters and 128 characters. The completion-event schema is exactly `event`, `request_id`, `method`, `path`, `status_code`, and `duration_ms`; no client-supplied query parameters, request body, headers, credentials, or exception text are logged. A missing/invalid identifier cannot fail a request.

## Compatibility

No persistence, migration, API behavior, or external integration changes. New routes are additive. Existing middleware continues to apply.

## Validation

Focused `test_main_runtime.py` tests map AC-001 through AC-007, including 4xx, generic 5xx, ID validation, redaction, and injection resistance. Full backend, frontend lint/tests/build, and mocked E2E run only in clean reproducible environments, with receipts persisted before the slice can freeze.
