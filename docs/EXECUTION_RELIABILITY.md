# Execution Reliability

E13DB-002 introduces `ReliableAuditRunner`: explicit `PENDING → RUNNING → SUCCESS|FAILED|INTERRUPTED` transitions, target-isolated results, bounded transient retries with exponential backoff, check/run deadlines, and cancellation that never yields success.

`SqliteExecutionLease` is an additive durable lease for scheduler idempotency and restart recovery. A holder may recover expired `RUNNING` entries as `INTERRUPTED`; active leases reject duplicate execution keys. Database adapters must still set driver-level connection/query timeouts because a timed-out Python thread cannot safely be force-killed.
