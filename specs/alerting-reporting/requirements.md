# Alerting and reporting requirements

## Problem and actors
Operators need actionable operational changes without opening every audit. A USER reviews, acknowledges, suppresses and closes alerts; the service produces reports from persisted audit evidence.

## Requirements
- **AR-1** Persist deterministic alert events, actions and delivery attempts; deduplicate persistent conditions.
- **AR-2** Apply priority policy, cooldown, escalation and maintenance suppression while retaining event evidence.
- **AR-3** Expose authenticated alert and notification-health APIs; unsafe actions require CSRF.
- **AR-4** Produce persisted daily and weekly reports in one data model with Markdown, HTML and JSON payloads, including aging findings and optional SMTP delivery status.
- **AR-5** Use the existing SMTP configuration without storing or exposing credentials; redact delivery errors.
- **AR-6** Provide an operator UI for active alerts, actions, report generation and preview.

## Acceptance criteria
AR-1 is met when 20 unchanged P1 evaluations produce one initial delivery. AR-2 is met when P2-to-P1 escalation can re-notify and a maintenance period suppresses delivery. AR-3 is met when anonymous requests fail and CSRF-less actions fail. AR-4 is met when both period types persist and include fleet/audit/aging data. AR-5 is met when a failing channel stores a redacted reason. AR-6 is met when the Alerts & Reports workspace is buildable.

## Constraints and non-goals
No second scheduler, external notification channel, PDF renderer, or secret persistence is introduced. Scheduler integration is represented by the existing lifecycle and reports may be generated from a scheduled automation hook in a follow-up configuration surface.
