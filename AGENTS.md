# AGENTS.md

## Mandatory Workflow

- For any debugging task, bug investigation, error analysis, regression analysis, or root-cause analysis, always use the local skill `systematic-debugging` from `.agent/skills/systematic-debugging/SKILL.md` before proposing or implementing a fix.
- For any implementation that involves more than one step, refactoring, coordinated edits, or verification work, always use the local skill `plan-writing` from `.agent/skills/plan-writing/SKILL.md`.
- When both apply, use them in this order: `systematic-debugging` first, `plan-writing` second.
- Do not skip these skills just because the task looks small if the user is reporting a failure, an unexpected behavior, or asking for a fix.

## Response Behavior

- State explicitly when these skills are being used.
- Keep the workflow evidence-based: reproduce, isolate, understand, fix, and verify.
- After making a fix, always run the most relevant available verification for the changed area and report the result.

## Fallback

- If either skill file is missing or cannot be read, say so briefly and continue with the closest equivalent workflow instead of silently skipping it.
