# Update Lots Bootstrap

## Goal
Publish the updated lots and schema mapping inventory through tracked bootstrap data.

## Tasks
- [x] Export local `schema_lots` and `master_lots` into `resources/bootstrap/initial_data.json` -> Verify JSON counts match local SQLite.
- [x] Validate no local SQLite or secret files are staged -> Verify `git status --ignored` and staged names.
- [x] Run focused mapping/bootstrap tests -> Verify pytest passes.
- [x] Commit and push to `origin/main` -> Verify remote head matches local commit.

## Done When
- [x] GitHub `main` contains the updated public lots and mapping bootstrap data.
