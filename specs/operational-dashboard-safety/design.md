# Design

## Current-state evidence

`AutomationDashboardPanel` is historical/monthly only. `AutomationHistoryPanel` has no delivery-attempt drill-down and enables retry from `!email_sent`. `enqueue_manual_retry` only verifies that the run exists. The store already exposes bounded, run-filtered delivery attempts.

## Proposed change

1. Add a small status/relative-time utility module shared by operational panels.
2. Enrich the dashboard with an operational overview calculated from loaded runs/retry queue; retain monthly analytics below it.
3. Fetch delivery attempts only when a run is expanded. Merge their latest status into a read-only retry-policy decision returned to the panel.
4. Add the same policy decision in `AutomationService.enqueue_manual_retry`, before enqueueing. The API is the final authority.
5. Re-evaluate that policy at `process_retry_queue_item` so a stale or externally inserted queue item cannot bypass the enqueue boundary. Rejection updates only the queue item to failed/manual-review; it does not synchronize or alter the original delivery attempt.
6. Processors claim a `pending` retry item through one conditional store update before payload construction or SMTP. A failed claim is a benign no-op, which prevents two manual callers from sending the same item.

## Retry policy

| Latest delivery status | UI/API decision |
| --- | --- |
| `failed` | eligible |
| `sent` | blocked: already delivered |
| `in_progress` | blocked: active operation |
| `unknown_delivery_outcome` or unrecognized | blocked: external result unknown |
| absent | blocked: no observed attempt |

## Failure and security handling

The frontend displays only server-provided safe messages and existing sanitized error fields. It does not construct or disclose SMTP details. Unknown states fail closed. Existing queue scheduling, SMTP delivery runtime, reconciliation, correlation, CAS, and sanitization are untouched; processing adds the same fail-closed eligibility gate used at enqueue plus a durable manual claim. The manual claim uses the same durable queue state as the automatic processor; it is not an in-memory lock.

## Verification strategy

Frontend unit tests cover policy decisions and key panel states. Backend tests establish the manual-retry status matrix, permitted failed retry, independently enforced processing gate, and two concurrent manual processors against one queue item with a blocked SMTP stub. Then run relevant frontend tests, automation tests, and full pytest regression.
