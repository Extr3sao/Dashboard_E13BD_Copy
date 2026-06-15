from src.api.post_crq_audit import (
    _build_wrapped_sql,
    _days_back_from_filter,
    parse_post_crq_checks,
    resolve_post_crq_markdown_path,
    _sql_with_binds,
)


def test_wrapped_sql_prefers_visible_schema_alias_over_inner_owner_alias():
    checks = parse_post_crq_checks(resolve_post_crq_markdown_path())

    for item in checks:
      wrapped_sql, _, schema_alias, _, schema_pushed, _ = _build_wrapped_sql(
          item.get("sql") or "",
          {"mode": "preset"},
          ["ABOIX"],
          {},
      )
      assert schema_alias != "OWNER", item.get("check_id")
      assert 'post_crq_result."OWNER"' not in wrapped_sql
      if schema_pushed:
          assert 'post_crq_result."ESQUEMA"' in wrapped_sql or 'post_crq_result."SCHEMA"' in wrapped_sql or 'post_crq_result."SCHEMA_NAME"' in wrapped_sql


def test_wrapped_sql_uses_visible_temporal_alias_instead_of_cte_params_alias():
    sql = """
    WITH params AS (
        SELECT
            TO_DATE(:start_date, 'YYYY-MM-DD') AS start_date,
            TO_DATE(:end_date, 'YYYY-MM-DD') AS end_date
        FROM dual
    )
    SELECT
        owner AS esquema,
        last_ddl_time AS fecha_modif
    FROM dba_objects
    """

    wrapped_sql, _, _, temporal_alias, _, time_pushed = _build_wrapped_sql(
        sql,
        {"mode": "range", "start_date": "2026-04-01", "end_date": "2026-04-07"},
        [],
        {"start_date": "2026-04-01", "end_date": "2026-04-07"},
    )

    assert time_pushed is True
    assert temporal_alias == "FECHA_MODIF"
    assert 'post_crq_result."FECHA_MODIF"' in wrapped_sql
    assert 'post_crq_result."START_DATE"' not in wrapped_sql


def test_sql_with_binds_removes_quotes_around_substitution_date_variables():
    sql = """
    SELECT
        TO_DATE('&START_DATE', 'YYYY-MM-DD') AS start_date,
        TO_DATE('&END_DATE', 'YYYY-MM-DD') AS end_date
    FROM dual
    """

    rendered = _sql_with_binds(sql)

    assert "TO_DATE(:start_date, 'YYYY-MM-DD')" in rendered
    assert "TO_DATE(:end_date, 'YYYY-MM-DD')" in rendered
    assert "':start_date'" not in rendered
    assert "':end_date'" not in rendered


def test_sql_with_binds_supports_explicit_datetime_binds():
    sql = """
    SELECT
        TO_DATE('&START_AT', 'YYYY-MM-DD HH24:MI:SS') AS start_at,
        TO_DATE('&END_AT', 'YYYY-MM-DD HH24:MI:SS') AS end_at
    FROM dual
    """

    rendered = _sql_with_binds(sql)

    assert "TO_DATE(:start_at, 'YYYY-MM-DD HH24:MI:SS')" in rendered
    assert "TO_DATE(:end_at, 'YYYY-MM-DD HH24:MI:SS')" in rendered
    assert "':start_at'" not in rendered
    assert "':end_at'" not in rendered


def test_wrapped_sql_ignores_cte_aliases_in_current_check_01_sql():
    checks = parse_post_crq_checks(resolve_post_crq_markdown_path())
    check_01 = next(item for item in checks if item.get("check_id") == "CHECK_01")

    wrapped_sql, _, _, temporal_alias, _, time_pushed = _build_wrapped_sql(
        _sql_with_binds(check_01.get("sql") or ""),
        {"mode": "range", "start_date": "2026-04-01", "end_date": "2026-04-07"},
        [],
        {"start_date": "2026-04-01", "end_date": "2026-04-07"},
    )

    assert temporal_alias == "FECHA_MODIF"
    assert time_pushed is False
    assert 'post_crq_result."START_DATE"' not in wrapped_sql
    assert 'post_crq_result."END_DATE"' not in wrapped_sql


def test_days_back_range_preserves_date_window_and_explicit_hours():
    days_back, normalized = _days_back_from_filter(
        {"mode": "range", "start_date": "2026-03-24T09:30", "end_date": "2026-03-25T08:30"},
        reference_dt=__import__("datetime").datetime(2026, 3, 25, 8, 30),
    )

    assert days_back == 2
    assert normalized["start_date"] == "2026-03-24"
    assert normalized["end_date"] == "2026-03-25"
    assert normalized["range_start_at"] == "2026-03-24T09:30"
    assert normalized["range_end_at"] == "2026-03-25T08:30"


def test_wrapped_sql_pushes_precise_time_window_when_hours_are_present():
    sql = 'SELECT OWNER AS ESQUEMA, LAST_DDL_TIME AS FECHA_MODIF FROM DBA_OBJECTS'

    wrapped_sql, binds, _, temporal_alias, _, time_pushed = _build_wrapped_sql(
        sql,
        {
            "mode": "range",
            "start_date": "2026-03-24",
            "end_date": "2026-03-25",
            "range_start_at": "2026-03-24T09:30",
            "range_end_at": "2026-03-25T08:30",
        },
        [],
        {},
    )

    assert temporal_alias == "FECHA_MODIF"
    assert time_pushed is True
    assert 'post_crq_result."FECHA_MODIF" BETWEEN TO_DATE(:start_at, \'YYYY-MM-DD HH24:MI:SS\')' in wrapped_sql
    assert binds["start_at"] == "2026-03-24 09:30:00"
    assert binds["end_at"] == "2026-03-25 08:30:00"
