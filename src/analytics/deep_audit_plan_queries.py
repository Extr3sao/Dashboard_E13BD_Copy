from typing import Dict


class DeepAuditPlanQueries:
    """SQL del pla d'auditoria profunda (Q01-Q19) amb paràmetres bind d'Oracle."""

    @staticmethod
    def common_params(schema_name: str) -> Dict[str, object]:
        return {
            "schema_name": schema_name.upper(),
            "ddl_days": 180,
            "stats_days": 30,
            "mods_days": 30,
            "login_recent_days": 90,
            "jobs_recent_days": 90,
            "size_min_gb": 1,
            "size_high_gb": 10,
        }

    Q01_SUMMARY_360 = """
    WITH params AS (
      SELECT
        :ddl_days AS ddl_days,
        :stats_days AS stats_days,
        :mods_days AS mods_days,
        :login_recent_days AS login_recent_days,
        :jobs_recent_days AS jobs_recent_days,
        :size_min_gb AS size_min_gb,
        :size_high_gb AS size_high_gb
      FROM dual
    ),
    seg AS (
      SELECT owner, ROUND(SUM(bytes)/1024/1024/1024, 2) AS size_gb
      FROM dba_segments
      GROUP BY owner
    ),
    o AS (
      SELECT owner, COUNT(*) AS object_count
      FROM dba_objects
      GROUP BY owner
    ),
    a AS (
      SELECT username,
             NVL(ROUND(SYSDATE - CAST(last_login AS DATE), 0), 999) AS last_login_days_ago
      FROM dba_users
    ),
    ddl AS (
      SELECT owner,
             (SYSDATE - MAX(last_ddl_time)) AS days_since_newest_ddl,
             SUM(CASE WHEN last_ddl_time >= SYSDATE - (SELECT ddl_days FROM params) THEN 1 ELSE 0 END) AS ddl_recent_cnt
      FROM dba_objects
      GROUP BY owner
    ),
    stats AS (
      SELECT owner, COUNT(*) AS tables_stats_recent
      FROM dba_tables
      WHERE last_analyzed >= SYSDATE - (SELECT stats_days FROM params)
      GROUP BY owner
    ),
    mods AS (
      SELECT table_owner AS owner, COUNT(*) AS tables_with_mods
      FROM dba_tab_modifications
      WHERE NVL("TIMESTAMP", DATE '1900-01-01') >= SYSDATE - (SELECT mods_days FROM params)
      GROUP BY table_owner
    ),
    j AS (
      SELECT owner,
             SUM(CASE WHEN enabled = 'TRUE' AND NVL(state,'') <> 'DISABLED' THEN 1 ELSE 0 END) AS active_jobs,
             SUM(CASE WHEN last_start_date >= SYSDATE - (SELECT jobs_recent_days FROM params) THEN 1 ELSE 0 END) AS jobs_started_recent
      FROM dba_scheduler_jobs
      GROUP BY owner
    ),
    ap AS (
      SELECT owner, COUNT(*) AS apex_applications
      FROM apex_applications
      GROUP BY owner
    ),
    d_out AS (
      SELECT owner, COUNT(*) AS external_dependencies_out
      FROM dba_dependencies
      WHERE owner <> referenced_owner
      GROUP BY owner
    ),
    d_in AS (
      SELECT referenced_owner AS owner, COUNT(*) AS inbound_references
      FROM dba_dependencies
      WHERE owner <> referenced_owner
      GROUP BY referenced_owner
    ),
    trg AS (
      SELECT owner, COUNT(*) AS enabled_triggers
      FROM dba_triggers
      WHERE status = 'ENABLED'
      GROUP BY owner
    )
    SELECT
      u.username,
      u.account_status,
      ROUND(SYSDATE - u.created, 0) AS days_old,
      NVL(seg.size_gb, 0) AS size_gb,
      NVL(o.object_count, 0) AS object_count,
      NVL(a.last_login_days_ago, 999) AS last_login_days,
      NVL(j.active_jobs, 0) AS active_jobs,
      NVL(ap.apex_applications, 0) AS apex_applications,
      NVL(d_out.external_dependencies_out, 0) AS external_dependencies_out,
      NVL(d_in.inbound_references, 0) AS inbound_references,
      NVL(ddl.days_since_newest_ddl, 999) AS days_since_newest_ddl,
      NVL(stats.tables_stats_recent, 0) AS tables_stats_recent_30d,
      NVL(mods.tables_with_mods, 0) AS tables_with_mods_30d,
      NVL(j.jobs_started_recent, 0) AS jobs_started_recent,
      NVL(trg.enabled_triggers, 0) AS enabled_triggers,
      CASE WHEN (NVL(mods.tables_with_mods, 0) > 0 OR NVL(stats.tables_stats_recent, 0) > 0 OR NVL(ddl.ddl_recent_cnt, 0) > 0 OR NVL(a.last_login_days_ago, 999) < (SELECT login_recent_days FROM params)) THEN 1 ELSE 0 END AS alarm_1_activity_recent,
      CASE WHEN (NVL(j.active_jobs, 0) > 0 OR NVL(j.jobs_started_recent, 0) > 0) THEN 1 ELSE 0 END AS alarm_2_jobs,
      CASE WHEN NVL(ap.apex_applications, 0) > 0 THEN 1 ELSE 0 END AS alarm_3_apex,
      CASE WHEN NVL(d_out.external_dependencies_out, 0) > 0 THEN 1 ELSE 0 END AS alarm_4_external_deps,
      CASE WHEN NVL(d_in.inbound_references, 0) > 0 THEN 1 ELSE 0 END AS alarm_5_inbound_refs,
      CASE WHEN NVL(trg.enabled_triggers, 0) > 0 THEN 1 ELSE 0 END AS alarm_6_triggers
    FROM dba_users u
    LEFT JOIN seg ON seg.owner = u.username
    LEFT JOIN o ON o.owner = u.username
    LEFT JOIN a ON a.username = u.username
    LEFT JOIN ddl ON ddl.owner = u.username
    LEFT JOIN stats ON stats.owner = u.username
    LEFT JOIN mods ON mods.owner = u.username
    LEFT JOIN j ON j.owner = u.username
    LEFT JOIN ap ON ap.owner = u.username
    LEFT JOIN d_out ON d_out.owner = u.username
    LEFT JOIN d_in ON d_in.owner = u.username
    LEFT JOIN trg ON trg.owner = u.username
    WHERE u.username = :schema_name
    """

    Q02_SIZE = """
    SELECT owner AS esquema,
           ROUND(SUM(bytes)/1024/1024/1024,2) AS size_gb,
           COUNT(*) AS segment_count
    FROM dba_segments
    WHERE owner = :schema_name
    GROUP BY owner
    ORDER BY size_gb DESC
    """

    Q03_USER_ACCOUNT = """
    SELECT username, created, last_login, account_status, lock_date, expiry_date,
           default_tablespace, temporary_tablespace, profile
    FROM dba_users
    WHERE username = :schema_name
    """

    Q04_ACTIVITY_CLASS = """
    WITH owners AS (
      SELECT username AS owner
      FROM dba_users
      WHERE username = :schema_name
    ),
    ddl AS (
      SELECT owner, COUNT(*) AS ddl_recent
      FROM dba_objects
      WHERE owner IN (SELECT owner FROM owners)
        AND last_ddl_time >= SYSDATE - :ddl_days
      GROUP BY owner
    ),
    stats AS (
      SELECT owner, COUNT(*) AS tables_stats_recent
      FROM dba_tables
      WHERE owner IN (SELECT owner FROM owners)
        AND last_analyzed >= SYSDATE - :stats_days
      GROUP BY owner
    ),
    mods AS (
      SELECT table_owner AS owner, COUNT(*) AS tables_with_mods
      FROM dba_tab_modifications
      WHERE table_owner IN (SELECT owner FROM owners)
        AND NVL("TIMESTAMP", DATE '1900-01-01') >= SYSDATE - :mods_days
      GROUP BY table_owner
    )
    SELECT o.owner,
           NVL(d.ddl_recent, 0) AS ddl_recent,
           NVL(s.tables_stats_recent, 0) AS tables_stats_recent,
           NVL(m.tables_with_mods, 0) AS tables_with_mods,
           CASE
             WHEN NVL(m.tables_with_mods, 0) > 0 THEN 'NO ELIMINAR'
             WHEN NVL(m.tables_with_mods, 0) = 0 AND NVL(d.ddl_recent, 0) > 0 THEN 'PRECAUCIO'
             ELSE 'ELIMINAR'
           END AS resultat
    FROM owners o
    LEFT JOIN ddl d ON d.owner = o.owner
    LEFT JOIN stats s ON s.owner = o.owner
    LEFT JOIN mods m ON m.owner = o.owner
    """

    Q05_OBJECTS_BY_TYPE = """
    SELECT owner, object_type, COUNT(*) AS quantity,
           MIN(created) AS oldest_created,
           MAX(created) AS newest_created,
           MIN(last_ddl_time) AS oldest_ddl,
           MAX(last_ddl_time) AS newest_ddl
    FROM dba_objects
    WHERE owner = :schema_name
    GROUP BY owner, object_type
    ORDER BY owner, newest_ddl DESC
    """

    Q06_RECENT_DDL = """
    SELECT owner, object_name, object_type, created, last_ddl_time, status
    FROM dba_objects
    WHERE owner = :schema_name
      AND last_ddl_time >= SYSDATE - :ddl_days
    ORDER BY last_ddl_time DESC
    """

    Q07_TABLE_STATS = """
    SELECT owner, table_name, num_rows, last_analyzed, sample_size,
           ROUND(SYSDATE - last_analyzed,0) AS days_since_analyzed
    FROM dba_tables
    WHERE owner = :schema_name
      AND last_analyzed IS NOT NULL
    ORDER BY last_analyzed DESC
    """

    Q08_DEPS_INCOMING = """
    SELECT owner AS dependent_owner,
           name AS dependent_name,
           type AS dependent_type,
           referenced_owner,
           referenced_name,
           referenced_type,
           dependency_type
    FROM dba_dependencies
    WHERE referenced_owner = :schema_name
      AND owner <> :schema_name
    ORDER BY dependent_owner, referenced_owner
    """

    Q09_DEPS_OUTGOING = """
    SELECT owner, name, type, referenced_owner, referenced_name, referenced_type, dependency_type
    FROM dba_dependencies
    WHERE owner = :schema_name
      AND referenced_owner <> :schema_name
    ORDER BY referenced_owner, owner
    """

    Q10_SYNONYMS = """
    SELECT owner, synonym_name, table_owner, table_name, db_link
    FROM dba_synonyms
    WHERE owner = :schema_name
       OR table_owner = :schema_name
    ORDER BY owner, table_owner, table_name
    """

    Q11_GRANTS_GIVEN = """
    SELECT grantor, privilege, grantee, owner, table_name, grantable, hierarchy
    FROM dba_tab_privs
    WHERE grantor = :schema_name
    ORDER BY grantee, grantor
    """

    Q12_GRANTS_RECEIVED = """
    SELECT grantor, privilege, grantee, owner, table_name, grantable, hierarchy
    FROM dba_tab_privs
    WHERE grantee = :schema_name
      AND grantor <> :schema_name
    ORDER BY grantor, privilege
    """

    Q13_SYS_PRIVS = """
    SELECT grantee, privilege, admin_option, common, inherited
    FROM dba_sys_privs
    WHERE grantee = :schema_name
    ORDER BY privilege
    """

    Q14_CODE_REFS_SOURCE = """
    SELECT owner, name, type
    FROM dba_source
    WHERE UPPER(text) LIKE UPPER('%' || :schema_name || '.%')
      AND owner NOT IN ('SYS','SYSTEM', :schema_name)
    FETCH FIRST 200 ROWS ONLY
    """

    Q14_CODE_REFS_VIEWS = """
    SELECT owner, view_name AS name, 'VIEW' AS type
    FROM dba_views
    WHERE UPPER(text_vc) LIKE UPPER('%' || :schema_name || '.%')
      AND owner NOT IN ('SYS','SYSTEM', :schema_name)
    FETCH FIRST 200 ROWS ONLY
    """

    Q14_CODE_REFS_TRIGGERS = """
    SELECT owner, trigger_name AS name, 'TRIGGER' AS type
    FROM dba_triggers
    WHERE UPPER(NVL(when_clause,' ')) LIKE UPPER('%' || :schema_name || '.%')
      AND owner NOT IN ('SYS','SYSTEM', :schema_name)
    FETCH FIRST 200 ROWS ONLY
    """

    Q15_JOBS = """
    SELECT owner, job_name, enabled, state, last_start_date, next_run_date
    FROM dba_scheduler_jobs
    WHERE owner = :schema_name
    ORDER BY owner, job_name
    """

    Q16_TRIGGERS_ENABLED = """
    SELECT owner, trigger_name, table_owner, table_name, status, triggering_event
    FROM dba_triggers
    WHERE owner = :schema_name
      AND status = 'ENABLED'
    ORDER BY owner, trigger_name
    """

    Q17_APEX_APPS = """
    SELECT workspace, application_id, application_name, owner, last_updated_on
    FROM apex_applications
    WHERE owner = :schema_name
    ORDER BY owner, application_id
    """

    Q18_DB_LINKS = """
    SELECT owner, db_link, username, host, created
    FROM dba_db_links
    WHERE owner = :schema_name OR owner = 'PUBLIC'
    ORDER BY owner, db_link
    """

    Q19_INVALID_OBJECTS = """
    SELECT owner, object_name, object_type, status, last_ddl_time
    FROM dba_objects
    WHERE owner = :schema_name
      AND status <> 'VALID'
    ORDER BY owner, object_type, object_name
    """
