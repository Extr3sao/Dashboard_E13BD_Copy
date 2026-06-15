class OracleQueries:
    @staticmethod
    def get_summary_query(whitelist_schemas):
        """Resum executiu d'esquemes per a l'auditoria inicial."""
        schemas_str = "', '".join(whitelist_schemas)
        return f"""
        SELECT u.username,
               u.account_status,
               ROUND(SYSDATE - u.created, 0) as days_old,
               s.size_gb,
               o.object_count,
               COALESCE(a.last_login_days_ago, 999) as last_login_days_ago,
               COALESCE(j.active_jobs, 0) as active_jobs,
               COALESCE(ap.apex_apps, 0) as apex_applications,
               COALESCE(d.external_dependencies, 0) as external_dependencies
        FROM dba_users u
        LEFT JOIN (
            SELECT owner, ROUND(SUM(bytes)/1024/1024/1024, 2) AS size_gb
            FROM dba_segments GROUP BY owner
        ) s ON u.username = s.owner
        LEFT JOIN (
            SELECT owner, COUNT(*) as object_count
            FROM dba_objects GROUP BY owner
        ) o ON u.username = o.owner
        LEFT JOIN (
            SELECT username, ROUND(SYSDATE - CAST(last_login AS DATE), 0) AS last_login_days_ago 
            FROM dba_users 
            WHERE last_login >= SYSDATE - 365
        ) a ON u.username = a.username
        LEFT JOIN (
            SELECT owner, COUNT(*) as active_jobs
            FROM dba_scheduler_jobs 
            WHERE enabled = 'TRUE' AND state != 'DISABLED'
            GROUP BY owner
        ) j ON u.username = j.owner
        LEFT JOIN (
            SELECT owner, COUNT(*) as apex_apps
            FROM apex_applications GROUP BY owner
        ) ap ON u.username = ap.owner
        LEFT JOIN (
            SELECT referenced_owner, COUNT(*) as external_dependencies
            FROM dba_dependencies 
            WHERE owner NOT IN ('SYS', 'SYSTEM', 'XDB', 'APEX_200200')
              AND owner NOT IN ('{schemas_str}')
            GROUP BY referenced_owner
        ) d ON u.username = d.referenced_owner
        WHERE u.username IN ('{schemas_str}')
        ORDER BY last_login_days_ago ASC, size_gb DESC
        """

    @staticmethod
    def get_dependencies_query(whitelist_schemas):
        """Detecta bloquejos per dependències externes detallades."""
        schemas_str = "', '".join(whitelist_schemas)
        return f"""
        SELECT owner as dependent_owner, name as dependent_name, type as dependent_type, 
               referenced_owner, referenced_name, referenced_type
        FROM dba_dependencies 
        WHERE referenced_owner IN ('{schemas_str}')
          AND owner NOT IN ('{schemas_str}', 'SYS', 'SYSTEM', 'XDB')
        """

    @staticmethod
    def get_active_components_query(whitelist_schemas):
        """Identifica Jobs i Triggers actius."""
        schemas_str = "', '".join(whitelist_schemas)
        return f"""
        SELECT owner, 'JOB' as COMPONENT_TYPE, job_name as COMPONENT_NAME, state as STATUS
        FROM dba_scheduler_jobs 
        WHERE owner IN ('{schemas_str}') AND enabled = 'TRUE'
        UNION ALL
        SELECT owner, 'TRIGGER' as COMPONENT_TYPE, trigger_name as COMPONENT_NAME, status as STATUS
        FROM dba_triggers
        WHERE owner IN ('{schemas_str}') AND status = 'ENABLED'
        """

    @staticmethod
    def get_apex_audit_query(whitelist_schemas):
        """Revisa aplicacions APEX vinculades."""
        schemas_str = "', '".join(whitelist_schemas)
        return f"""
        SELECT workspace, application_id, application_name, owner, last_updated_on
        FROM apex_applications 
        WHERE owner IN ('{schemas_str}')
        """
