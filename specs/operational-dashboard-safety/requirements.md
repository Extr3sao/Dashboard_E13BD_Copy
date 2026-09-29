# Operational dashboard safety

## Context

The Automation dashboard already exposes run history, lot outcomes, a retry queue, and delivery-attempt data. Its current retry action is enabled from `!email_sent`, while the API accepts a manual retry without checking the delivery state. This can enqueue a resend for a delivery that is not safely retryable.

## Goals

- Make retry eligibility explicit and enforce the existing safe-retry contract at the API boundary.
- Make the operational home and run explorer surface active work, delivery failures, and retry context with fewer navigation steps.
- Keep existing delivery behavior, sanitization, and automation contracts intact.

## Non-goals

- No automatic retry behavior changes, SMTP changes, database migration, or WebSocket introduction.
- No new metrics whose source data is not present.

## Actors and journeys

- An operator opens Automation, identifies items needing attention, drills into a run, and sees delivery/retry context.
- An operator attempts a resend and sees either a safe explanation or a retry action that is eligible under policy.

## Requirements

- FR-001: The dashboard MUST summarize current runs and retry work from existing run and retry-queue data.
- FR-002: A run detail MUST show start, end, duration, run identifier, artifacts/reports when available, lot delivery result, and retry eligibility context.
- FR-003: The retry UI MUST explain why retry is available or blocked without relying only on color.
- FR-004: Manual retry enqueueing MUST only be allowed when the latest matching delivery outcome is `failed`; `sent`, `in_progress`, and `unknown_delivery_outcome` MUST be rejected.
- FR-005: A missing delivery-attempt record MUST be rejected for manual retry, since it cannot establish safe eligibility.
- FR-006: Retry processing MUST independently reject an already-queued item unless its latest matching durable delivery attempt is `failed`, without invoking SMTP or mutating that original attempt.
- FR-007: Both manual and due-queue retry processing MUST acquire a durable, compare-and-set claim before sending. A caller that does not acquire the claim MUST perform no SMTP action.
- NFR-001: Existing API calls and table limits MUST remain bounded; run-specific delivery detail MUST load only on drill-down.
- NFR-002: Safe UI error content MUST not expose raw SMTP credentials or transport traces.
- NFR-003: Concurrent processing of the same retry item MUST result in at most one physical delivery attempt.
- CON-001: Existing retry processing and delivery state persistence remain authoritative; no automatic retry is introduced from the UI.

## Acceptance criteria

- AC-001: The dashboard displays counts for running, failed/partial runs, retry-pending work, and recent errors derived from loaded data.
- AC-002: Expanding a run displays a readable run identifier, relative/absolute time, duration, and delivery/retry detail or an explicit empty state.
- AC-003: A failed delivery can present an eligible retry action with its reason; sent, in-progress, unknown, and absent outcomes present a blocking reason and no enqueue action.
- AC-004: The retry endpoint returns a client error for sent, in-progress, unknown, or absent delivery outcomes and permits failed outcomes.
- AC-005: Focused frontend and backend tests pass, followed by the existing automation and full regressions.
- AC-006: The manual-retry matrix rejects absent, empty, unrecognized, sent, in-progress, and unknown outcomes without a queue side effect; it permits `failed`. A directly inserted unsafe queue item is rejected at processing before SMTP.
- AC-007: Two concurrent manual processors of one eligible pending queue item yield exactly one successful claim and at most one SMTP invocation; an unclaimable item is returned without mutation or false success.

## Assumptions

- The latest `delivery_attempts` row for `(run_id, lot, audience)` is the authoritative observed outcome. Existing status values are normalized only for the policy check; unrecognized values are treated as unknown and blocked.
