# Fix Oracle Thick Unicode Path

## Goal
Make Oracle Thick mode initialize even when the project path contains non-ASCII characters.

## Tasks
- [x] Reproduce Thick mode init failure with local `instantclient` path -> Verify `UnicodeDecodeError` appears.
- [x] Add Windows short-path fallback for Instant Client initialization -> Verify minimal script exits Thick mode.
- [x] Add focused regression test -> Verify pytest passes.
- [ ] Push the fix to GitHub -> Verify `origin/main` contains the commit.

## Done When
- [x] `oracledb.is_thin_mode()` becomes `False` before Oracle connections in this workspace.
