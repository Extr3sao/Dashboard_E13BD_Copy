# Design

`AlertingService` owns SQLite migrations and projects current `FindingStore` state into `alert_events`; identity is SHA-256 of target, type and source identity. `alert_deliveries`, maintenance windows and report history are indexed for bounded queries. Policy defaults are P1 immediate/one-hour cooldown, P2 immediate/four-hour cooldown, P3 digest and P4 dashboard only.

The Post-CRQ completion path evaluates alerts after reconciliation. `NotificationChannel` permits channel replacement; SMTP is adapted from the existing automation delivery configuration and delivery failure strings pass through `redact_secrets`. `/api/alerting` is USER protected, with CSRF on mutations. Reports query only the requested 24h/7d window and save JSON, Markdown and HTML representations from the same payload.

Failure handling stores failed attempts without raising from audit reconciliation. Maintenance only suppresses notification, never alert persistence. The UI is a lazy workspace view with compact alert actions and a readable Markdown preview.

Automatic reports use `AutomationService.run_scheduled_maintenance`, the existing scheduler tick, through an injected operational maintenance hook. It generates each report only when its persisted latest timestamp is due.
