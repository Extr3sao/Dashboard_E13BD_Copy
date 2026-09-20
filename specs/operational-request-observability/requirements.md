# Operational request observability

## Context

The FastAPI application exposes 97 endpoints but has no machine-readable liveness/readiness contract and no consistent request correlation identifier. Existing application logs are useful locally but do not consistently connect a client response to a server-side operation.

## Goals

- Provide dependency-free liveness and local readiness endpoints.
- Correlate every HTTP response with a safe request identifier and a completion log event.

## Non-goals

- Do not add authentication, change Oracle/SQLite connectivity semantics, or expose configuration, credentials, queries, or business data.
- Do not claim distributed tracing or deployment readiness beyond the local process contract.

## Requirements

- FR-001: The API MUST provide `GET /healthz`, returning a stable process liveness payload without external dependency calls.
- FR-002: The API MUST provide `GET /readyz`, returning a stable local-process readiness payload without external dependency calls.
- FR-003: The API MUST return an `X-Request-ID` header for every HTTP response, preserving only a safe client-provided identifier; invalid or absent identifiers MUST be replaced.
- FR-004: The API MUST preserve the observability contract for 4xx responses and unexpected 5xx responses.
- NFR-001: Completion logs MUST include event, request identifier, HTTP method, path, status, and duration, and MUST NOT include query strings or request bodies.
- NFR-002: Completion logs MUST redact credentials and secrets, including `Authorization`, cookies, passwords, tokens, and client-controlled log-injection content.
- CON-001: The change MUST preserve all existing API contracts and must not contact Oracle, SMTP, AI providers, or mutate business data.

## Acceptance criteria

- AC-001: `GET /healthz` returns HTTP 200 and exactly identifies the service as alive.
- AC-002: `GET /readyz` returns HTTP 200 and exactly identifies local process readiness.
- AC-003: A valid incoming `X-Request-ID` is returned unchanged; absent or invalid values receive a newly generated safe value.
- AC-004: A completion log event includes the specified safe fields and no query string.
- AC-005: Absent, malformed, oversized, and log-injection request IDs are replaced by generated safe UUIDs; valid bounded IDs are preserved.
- AC-006: 4xx and unexpected 5xx responses include `X-Request-ID` and emit exactly one completion event with HTTP status and non-negative duration.
- AC-007: Completion events contain only `event`, request ID, method, path, status code, and duration for request metadata; no query values, request bodies, authorization headers, cookies, passwords, tokens, or secrets are present.

## Assumptions

Readiness is intentionally process-local: Oracle and SMTP credentials are optional and may be unavailable in valid deployments. External dependency health remains a separately configured operational concern.

The route handlers themselves perform no external calls or business-data mutations. Application lifespan behavior is outside the endpoint contract and is exercised separately by the full regression suite.
