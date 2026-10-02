# E13DB-012 implementation plan

Certified starting revision: `review/e13db-product-architecture-devagent` at
`080bb7e395f8a030bc290b9d4ec237bb129293c8`.

1. Trace exact manual and scheduled Post-CRQ execution/report/reconciliation
   paths; preserve the existing Finding projection as the single reconciler.
2. Add backward-compatible AuditRun provenance columns, capability snapshot,
   per-attempt normalized RuleResults/evidence, and durable reconciliation
   receipts in the internal store. Add a stable AuditRun link to automation job
   runs and a recovery query for completed-but-unreconciled runs.
3. Normalize Post-CRQ output once and invoke the same evidence service for the
   manual API and AutomationService. Gate only explicitly declared rule
   requirements; never claim unavailable evidence as PASS.
4. Add durable notification outbox states for SMTP ambiguity, recover pending
   work without blind resend, and expose the delivery condition safely.
5. Add scheduled-path real application/browser fixture, parity, capability-loss,
   crash-point, idempotency and legacy migration tests. Update the operator UI
   and docs for AuditRun provenance.
6. Run complete backend/frontend/security/build and scale validation; commit and
   publish the feature branch only after the exact SHA is verified.

The local `plan-writing` skill required by AGENTS.md is unavailable; this file
and the tracked task list provide the equivalent implementation plan.
