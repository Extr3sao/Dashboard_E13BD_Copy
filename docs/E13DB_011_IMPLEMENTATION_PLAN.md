# E13DB-011 implementation plan

Certified base: `feature/e13db-010-cpd-operations` at
`653da8c14f0e7f8d6cb7c413603345c0facb3c9c`.

1. Inspect Finding/evidence schema, authenticated routes and browser navigation.
2. Add a bounded, indexed Oracle-first investigation store with normalized evidence,
   deterministic correlations, explainable hypotheses, safe next checks, plan
   observations, capacity trends, operator cause/resolution and recurrence lookup.
3. Trigger scoped automatic investigations from high-priority/worsening findings;
   expose USER/CSRF protected APIs and integrate Finding detail plus an
   investigation center/detail UI.
4. Add deterministic incident, contradiction, privacy, license/privilege,
   permission, recurrence, and query-boundedness tests. Document semantics.
5. Run the simulated DWH incident through recovery/reoccurrence, inspect UI,
   run complete regression/security/build, then commit and publish this branch.

Evidence semantics are explicit: facts are observations, correlations are
rule-based relationships, hypotheses remain operator-reviewable, and recommended
checks are non-destructive guidance. No probabilities or automatic root cause.

The mandatory local `plan-writing` skill is absent; this file and the session
work list provide the equivalent tracked plan.
