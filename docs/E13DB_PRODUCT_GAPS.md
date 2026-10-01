# E13DB product gaps (review 001–011)

| ID | Gap | User/DBA impact | Priority / closure evidence |
|---|---|---|---|
| PG-001 | Scheduled automation results do not flow through Finding reconciliation/alert evaluation | An unattended scheduled run can be green in job history while Fleet/Findings/Investigations do not represent its current results | P1; E13DB-012 must prove same stable AuditRun produces the same Findings from manual and scheduled execution |
| PG-002 | Ambiguous SMTP crash-after-accept | A resend may duplicate an email; the UI can lack a persisted SENT record after an accepted send | P1; outbox attempt and crash injection tests, including UNKNOWN rather than false retry certainty |
| PG-003 | No complete canonical RuleResult archive per audit path | Months later the DBA may have only Finding summaries/counts, not PASS/ERROR/skipped evidence for all rules | P1; replay/audit evidence export from one durable contract |
| PG-004 | Capability/privilege/rule-version snapshot absent per AuditRun | Absence of a Finding is not always distinguishable from a rule not eligible/available | P1; capability snapshot with explicit NOT_LICENSED/INSUFFICIENT_PRIVILEGES/UNKNOWN and rule version |
| PG-005 | No active Oracle collection in Investigations | The 011 correlations operate on stored Finding/audit observations; they do not query current V$ session/SQL/stats/segment views | P2; only after capability, privilege, timeout, row-limit and license authority are durable |
| PG-006 | No non-Oracle engines | Target identity and most check execution are profile/Oracle-oriented; changing UI labels does not provide portability | P2/FUTURE; target adapter boundaries first, PostgreSQL/SQL Server tests before claiming support |
| PG-007 | Resolved-case memory lacks operational retention controls | Case evidence and hypotheses can grow indefinitely; purging too aggressively destroys team knowledge | P2; retention must preserve operator-confirmed cause/actions and linked audit trail |
| PG-008 | Historical reproducibility manifest absent | Runtime, rule pack, configuration (secret-free), target version and capabilities cannot be reconstructed as a single record | P2; include hashes/versions in AuditRun and report export |
| PG-009 | Investigation classification is deterministic keyword/rule metadata | Useful and explainable, but findings with sparse evidence produce few/no hypotheses; no live data enrichment | P2; do not paper over with confidence scores or LLM guesses |
| PG-010 | Test certification artifacts not bound to each release SHA in a committed product receipt | CI output exists per session, but product operators cannot inspect one durable review receipt from the runtime | P3; a separate release-validation artifact can bind exact source SHA; keep it separate from operational truth |

## Explicit negative conclusion

Multi-database support is a future product opportunity, not the next milestone.
The current higher-value issue is consistent durable audit evidence and delivery
reconciliation inside the Oracle workflow that already exists.
