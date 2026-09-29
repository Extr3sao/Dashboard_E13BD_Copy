# Check Engine

E13DB-003 defines `RuleDefinition`, `RuleResult`, and `RuleEngine`. Rule status is one of `PASS`, `WARN`, `FAIL`, `ERROR`, or `SKIPPED`; error and skipped are never pass. Compatibility, privilege, capability, and license gates produce `SKIPPED`, while executor exceptions/timeouts produce isolated `ERROR` results.

The Post-CRQ adapter adds `rule_results` without changing legacy `executed_checks` or `results_by_check`: successful empty detection queries map to `PASS`, rows to `FAIL`, and legacy errors to `ERROR`. Normalized evidence excludes SQL and binds and recursively redacts credential-shaped values. `database_id` uses the existing profile label rather than a DSN.
