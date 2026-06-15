# Force Oracle Thick Mode

## Goal
Ensure every Oracle connection initializes python-oracledb Thick mode with Oracle Instant Client before connecting.

## Tasks
- [x] Add a central Oracle client initializer -> Verify imports use one path.
- [x] Update DB manager and Streamlit UI to require Thick mode -> Verify no silent Thin fallback remains.
- [x] Add tests for success, missing client path, and init failure -> Verify with pytest.
- [x] Run focused Oracle/config tests -> Verify all pass.

## Done When
- [x] Oracle connections either run in Thick mode or fail with a clear setup error before connecting.
