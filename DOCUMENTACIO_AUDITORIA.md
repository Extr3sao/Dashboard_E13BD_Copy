# Documentació Tècnica: Motor d'Auditoria d'Obsolescència (v3.2)

Aquest document detalla el funcionament intern del motor d'auditoria profunda i les consultes SQL que s'executen per determinar el risc d'obsolescència d'un esquema Oracle.

## 1. Funcionament General
L'auditoria realitza una anàlisi de 360 graus sobre l'esquema objectiu (`{username}`). Combina mètriques d'activitat real (logs), estadístiques del diccionari de dades i, el més important, una **cerca exhaustiva de dependències de codi** mitjançant patrons de wildcard.

## 2. Consultes SQL Executades
### 1.  un resum d'activitat, dependències, mida i ús real (DDL, DML, jobs, APEX, triggers, logins, etc.).
```sql

WITH params AS (
  SELECT
    180 AS ddl_days,
    30  AS stats_days,
    30  AS mods_days,
    90  AS login_recent_days,
    90  AS jobs_recent_days,
    1   AS size_min_gb,
    10  AS size_high_gb
  FROM dual
),

seg AS (
  SELECT owner, ROUND(SUM(bytes)/1024/1024/1024,2) AS size_gb
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
         COALESCE(ROUND(SYSDATE - CAST(last_login AS DATE),0), 999) AS last_login_days_ago
  FROM dba_users
),

ddl AS (
  SELECT owner,
         TRUNC(SYSDATE - MAX(last_ddl_time)) AS days_since_newest_ddl,
         SUM(
           CASE
             WHEN last_ddl_time >= SYSDATE - (SELECT ddl_days FROM params)
             THEN 1 ELSE 0
           END
         ) AS ddl_recent_cnt
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
  WHERE NVL("TIMESTAMP", DATE '1900-01-01')
        >= SYSDATE - (SELECT mods_days FROM params)
  GROUP BY table_owner
),

j AS (
  SELECT owner,
         SUM(
           CASE
             WHEN enabled = 'TRUE'
              AND NVL(state,'') <> 'DISABLED'
             THEN 1 ELSE 0
           END
         ) AS active_jobs,
         SUM(
           CASE
             WHEN last_start_date >= SYSDATE - (SELECT jobs_recent_days FROM params)
             THEN 1 ELSE 0
           END
         ) AS jobs_started_recent
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
),

resumen AS (
  SELECT
    u.username                                      AS username,
    u.account_status                                AS account_status,
    ROUND(SYSDATE - u.created, 0)                   AS days_old,

    COALESCE(seg.size_gb, 0)                        AS size_gb,
    COALESCE(o.object_count, 0)                     AS object_count,
    COALESCE(a.last_login_days_ago, 999)            AS last_login_days,

    COALESCE(j.active_jobs, 0)                      AS active_jobs,
    COALESCE(ap.apex_applications, 0)               AS apex_applications,

    COALESCE(d_out.external_dependencies_out, 0)    AS external_dependencies_out,
    COALESCE(d_in.inbound_references, 0)            AS inbound_references,

    COALESCE(ddl.days_since_newest_ddl, 999)        AS days_since_newest_ddl,
    COALESCE(stats.tables_stats_recent, 0)          AS tables_stats_recent_30d,
    COALESCE(mods.tables_with_mods, 0)              AS tables_with_mods_30d,
    COALESCE(j.jobs_started_recent, 0)              AS jobs_started_recent,
    COALESCE(trg.enabled_triggers, 0)               AS enabled_triggers,

    CASE
      WHEN COALESCE(mods.tables_with_mods, 0) > 0
        OR COALESCE(stats.tables_stats_recent, 0) > 0
        OR COALESCE(ddl.ddl_recent_cnt, 0) > 0
        OR COALESCE(a.last_login_days_ago, 999)
             < (SELECT login_recent_days FROM params)
      THEN 1 ELSE 0
    END                                             AS alarm_1_activity_recent,

    CASE
      WHEN COALESCE(j.active_jobs, 0) > 0
        OR COALESCE(j.jobs_started_recent, 0) > 0
      THEN 1 ELSE 0
    END                                             AS alarm_2_jobs,

    CASE WHEN COALESCE(ap.apex_applications, 0) > 0
         THEN 1 ELSE 0 END                           AS alarm_3_apex,

    CASE WHEN COALESCE(d_out.external_dependencies_out, 0) > 0
         THEN 1 ELSE 0 END                           AS alarm_4_external_deps,

    CASE WHEN COALESCE(d_in.inbound_references, 0) > 0
         THEN 1 ELSE 0 END                           AS alarm_5_inbound_refs,

    CASE WHEN COALESCE(trg.enabled_triggers, 0) > 0
         THEN 1 ELSE 0 END                           AS alarm_6_triggers,

    CASE
      WHEN seg.size_gb IS NULL THEN 'Desconegut'
      WHEN seg.size_gb <  (SELECT size_min_gb  FROM params) THEN 'mínim'
      WHEN seg.size_gb <= (SELECT size_high_gb FROM params) THEN 'moderat'
      WHEN seg.size_gb >  (SELECT size_high_gb FROM params) THEN 'alt'
      ELSE 'Desconegut'
    END                                             AS impacte_gb,

    CASE
      WHEN (
        COALESCE(mods.tables_with_mods, 0) > 0
        OR COALESCE(stats.tables_stats_recent, 0) > 0
        OR COALESCE(ddl.ddl_recent_cnt, 0) > 0
        OR COALESCE(a.last_login_days_ago, 999)
             < (SELECT login_recent_days FROM params)
        OR COALESCE(j.active_jobs, 0) > 0
        OR COALESCE(j.jobs_started_recent, 0) > 0
        OR COALESCE(ap.apex_applications, 0) > 0
        OR COALESCE(d_out.external_dependencies_out, 0) > 0
        OR COALESCE(d_in.inbound_references, 0) > 0
        OR COALESCE(trg.enabled_triggers, 0) > 0
      ) THEN 'NO ELIMINAR'
      WHEN COALESCE(ddl.ddl_recent_cnt, 0) > 0
      THEN 'PRECAUCIÓ'
      ELSE 'ELIMINAR'
    END                                             AS resultat

  FROM dba_users u
  LEFT JOIN seg   ON seg.owner = u.username
  LEFT JOIN o     ON o.owner   = u.username
  LEFT JOIN a     ON a.username = u.username
  LEFT JOIN ddl   ON ddl.owner = u.username
  LEFT JOIN stats ON stats.owner = u.username
  LEFT JOIN mods  ON mods.owner = u.username
  LEFT JOIN j     ON j.owner = u.username
  LEFT JOIN ap    ON ap.owner = u.username
  LEFT JOIN d_out ON d_out.owner = u.username
  LEFT JOIN d_in  ON d_in.owner = u.username
  LEFT JOIN trg   ON trg.owner = u.username
  WHERE u.username LIKE ('%{username}%') 
)

SELECT
  r.username                      AS "usuari / esquema",
  r.account_status                AS "estat del compte",
  r.days_old                      AS "dies d'antiguitat",
  r.size_gb                       AS "mida (GB)",
  r.object_count                  AS "nombre d'objectes",
  r.last_login_days               AS "dies des de l'últim inici de sessió",
  r.active_jobs                   AS "jobs actius",
  r.apex_applications             AS "aplicacions APEX",
  r.external_dependencies_out     AS "dependències sortints",
  r.inbound_references            AS "dependències entrants",
  r.days_since_newest_ddl         AS "dies des de l'últim DDL",
  r.tables_stats_recent_30d       AS "taules amb estadístiques recents (30 dies)",
  r.tables_with_mods_30d          AS "taules amb modificacions (30 dies)",
  r.jobs_started_recent           AS "jobs executats recentment",
  r.enabled_triggers              AS "triggers habilitats",

  r.alarm_1_activity_recent       AS "alarma: activitat recent",
  r.alarm_2_jobs                  AS "alarma: jobs",
  r.alarm_3_apex                  AS "alarma: APEX",
  r.alarm_4_external_deps         AS "alarma: dependències sortints",
  r.alarm_5_inbound_refs          AS "alarma: dependències entrants",
  r.alarm_6_triggers              AS "alarma: triggers",

  r.impacte_gb                    AS "impacte per mida",
  r.resultat                      AS "resultat final",

  f.review_alarms                 AS "resum d'alarmes",
  f.review_count                  AS "nombre d'alarmes"

FROM resumen r

CROSS JOIN LATERAL (
  SELECT
    LISTAGG(label, ' + ') WITHIN GROUP (ORDER BY ord) AS review_alarms,
    SUM(flag) AS review_count
  FROM (
    SELECT 1 AS ord,
           CASE WHEN r.alarm_1_activity_recent = 1
                THEN 'activitat recent' END AS label,
           CASE WHEN r.alarm_1_activity_recent = 1
                THEN 1 ELSE 0 END AS flag
    FROM dual
    UNION ALL
    SELECT 2,
           CASE WHEN r.alarm_2_jobs = 1
                THEN 'jobs actius' END,
           CASE WHEN r.alarm_2_jobs = 1
                THEN 1 ELSE 0 END
    FROM dual
    UNION ALL
    SELECT 3,
           CASE WHEN r.alarm_3_apex = 1
                THEN 'APEX' END,
           CASE WHEN r.alarm_3_apex = 1
                THEN 1 ELSE 0 END
    FROM dual
    UNION ALL
    SELECT 4,
           CASE WHEN r.alarm_4_external_deps = 1
                THEN 'dependències sortints' END,
           CASE WHEN r.alarm_4_external_deps = 1
                THEN 1 ELSE 0 END
    FROM dual
    UNION ALL
    SELECT 5,
           CASE WHEN r.alarm_5_inbound_refs = 1
                THEN 'dependències entrants' END,
           CASE WHEN r.alarm_5_inbound_refs = 1
                THEN 1 ELSE 0 END
    FROM dual
    UNION ALL
    SELECT 6,
           CASE WHEN r.alarm_6_triggers = 1
                THEN 'triggers' END,
           CASE WHEN r.alarm_6_triggers = 1
                THEN 1 ELSE 0 END
    FROM dual
  )
  WHERE label IS NOT NULL
) f

ORDER BY
  r.resultat,
  r.last_login_days NULLS LAST,
  r.size_gb DESC;

```
### 2. Calcula la mida total en GB que ocupa cada esquema a la base de dades i el nombre de segments que té.

```sql
SELECT
  owner                                             AS "esquema",
  ROUND(SUM(bytes)/1024/1024/1024,2)                AS "mida (GB)",
  COUNT(*)                                          AS "nombre de segments"
FROM dba_segments
WHERE owner LIKE ('%{username}%')
GROUP BY owner;
```

### 4. Aquesta consulta extrau la configuració tècnica, l'estat de seguretat i l'historial de connexió d'usuaris específics a la base de dades Oracle.

```sql
SELECT username             AS usuari, 
       created              AS data_creacio, 
       last_login           AS ultim_acces, 
       account_status       AS estat_compte, 
       lock_date            AS data_bloqueig, 
       expiry_date          AS data_caducitat, 
       default_tablespace   AS espai_taules_defecte,
       temporary_tablespace AS espai_taules_temporal, 
       profile              AS perfil
FROM dba_users 
WHERE username LIKE ('%{username}%')
```

### 5. Avalua l'activitat d'esquemes Oracle per classificar-los segons si s'han de conservar, revisar o eliminar basant-se en canvis recents de dades i estructures.

```sql
WITH owners AS (
  SELECT username AS owner
  FROM dba_users
  WHERE username LIKE ('%{username}%')
),

ddl AS (
  SELECT owner, COUNT(*) AS ddl_recent
  FROM dba_objects
  WHERE owner IN (SELECT owner FROM owners)
    AND last_ddl_time >= SYSDATE - 180
  GROUP BY owner
),

stats AS (
  SELECT owner, COUNT(*) AS tables_stats_recent
  FROM dba_tables
  WHERE owner IN (SELECT owner FROM owners)
    AND last_analyzed >= SYSDATE - 30
  GROUP BY owner
),

mods AS (
  SELECT table_owner AS owner, COUNT(*) AS tables_with_mods
  FROM dba_tab_modifications
  WHERE table_owner IN (SELECT owner FROM owners)
    AND NVL("TIMESTAMP", DATE '1900-01-01') >= SYSDATE - 30
  GROUP BY table_owner
)

SELECT
  o.owner                       AS propietari,
  NVL(d.ddl_recent, 0)          AS ddl_recent_180d,
  NVL(s.tables_stats_recent, 0)  AS estadistiques_recents_30d,
  NVL(m.tables_with_mods, 0)    AS taules_modificades_30d,
  CASE
    WHEN NVL(m.tables_with_mods, 0) > 0 THEN 'NO ELIMINAR'
    WHEN NVL(m.tables_with_mods, 0) = 0 AND NVL(d.ddl_recent, 0) > 0 THEN 'PRECAUCIÓ'
    ELSE 'ELIMINAR'
  END                           AS resultat
FROM owners o
LEFT JOIN ddl   d ON d.owner = o.owner
LEFT JOIN stats s ON s.owner = o.owner
LEFT JOIN mods  m ON m.owner = o.owner
ORDER BY
  CASE
    WHEN NVL(m.tables_with_mods, 0) > 0 THEN 1            
    WHEN NVL(d.ddl_recent, 0) > 0 THEN 2                 
    ELSE 3                                               
  END,
  o.owner;

```

### 6. agrupa i comptabilitza els objectes per propietari i tipus, tot mostrant les dates extremes de creació i de l'última modificació estructural.

```sql
SELECT owner             AS propietari, 
       object_type       AS tipus_objecte, 
       COUNT(*)          AS quantitat,
       MIN(created)      AS creacio_mes_antiga,
       MAX(created)      AS creacio_mes_recent,
       MIN(last_ddl_time) AS ddl_mes_antic,
       MAX(last_ddl_time) AS ddl_mes_recent
FROM dba_objects 
WHERE owner LIKE ('%{username}%')
GROUP BY owner, object_type
ORDER BY owner, ddl_mes_recent DESC;
```

### 7. llista els objectes modificats estructuralment durant els últims sis mesos, detallant-ne el tipus, la data i si estan actualment vàlids o invàlids.

```sql
SELECT owner         AS propietari, 
       object_name   AS nom_objecte, 
       object_type   AS tipus_objecte, 
       created       AS data_creacio, 
       last_ddl_time AS ultima_modificacio_ddl, 
       status        AS estat
FROM dba_objects 
WHERE owner LIKE ('%{username}%')
  AND last_ddl_time >= SYSDATE - 180
ORDER BY ultima_modificacio_ddl DESC;

```

### 8. mostra el volum de dades i la vigència de les estadístiques de les taules

```sql
SELECT owner                              AS propietari, 
       table_name                         AS nom_taula, 
       num_rows                           AS nombre_files, 
       last_analyzed                      AS ultima_analisi, 
       sample_size                        AS mida_mostra,
       ROUND((SYSDATE - last_analyzed),0) AS dies_des_de_l_analisi
FROM dba_tables 
WHERE owner LIKE ('%{username}%')
  AND last_analyzed IS NOT NULL
ORDER BY last_analyzed DESC;

```

### 9. identifica quins objectes externs depenen de l'esquema de l'usuari, essent crucial per evitar trencar funcionalitats en cas d'eliminar-lo.

```sql
SELECT owner             AS propietari_dependent, 
       name              AS nom_objecte, 
       type              AS tipus_objecte, 
       referenced_owner  AS propietari_referenciat, 
       referenced_name   AS nom_referenciat, 
       referenced_type   AS tipus_referenciat,
       dependency_type   AS tipus_dependencia
FROM dba_dependencies 
WHERE referenced_owner LIKE ('%{username}%')
  AND owner NOT LIKE ('%{username}%')
ORDER BY propietari_dependent, propietari_referenciat;
```


### 10. identifica de quins objectes externs depèn l'esquema de l'usuari, útil per saber quins permisos o accés a altres esquemes necessita per funcionar.

```sql
SELECT owner             AS propietari_objecte, 
       name              AS nom_objecte, 
       type              AS tipus_objecte, 
       referenced_owner  AS propietari_extern_referenciat, 
       referenced_name   AS nom_objecte_extern, 
       referenced_type   AS tipus_objecte_extern,
       dependency_type   AS tipus_dependencia
FROM dba_dependencies 
WHERE owner LIKE ('%{username}%')
  AND referenced_owner NOT LIKE ('%{username}%')
ORDER BY propietari_extern_referenciat, propietari_objecte;

```

### 11. llista els àlies (sinònims) que l'usuari ha creat per accedir més fàcilment a taules pròpies o d'altres propietaris, incloent-hi els accessos remots via DB Link.

```sql
SELECT owner        AS propietari_sinonim, 
       synonym_name AS nom_sinonim, 
       table_owner  AS propietari_taula, 
       table_name   AS nom_taula, 
       db_link      AS enllac_bd
FROM dba_synonyms 
WHERE owner LIKE ('%{username}%')
ORDER BY propietari_taula, nom_taula;

```

### 12. llista els permisos que l'usuari ha concedit a altres sobre els seus propis objectes, detallant qui ha rebut el permís i si aquest pot ser delegat.

```sql
SELECT grantor    AS otorgant, 
       privilege  AS privilegi, 
       grantee    AS beneficiari, 
       owner      AS propietari_objecte, 
       table_name AS nom_taula, 
       grantable  AS delegable, 
       hierarchy  AS jerarquia
FROM dba_tab_privs 
WHERE grantor LIKE ('%{username}%')
ORDER BY beneficiari, otorgant;
```

### 13. Detalla els permisos sobre objectes externs que han estat concedits a l'usuari, identificant qui li ha donat l'accés i sobre quines taules o vistes.

```sql

SELECT grantor    AS otorgant, 
       privilege  AS privilegi, 
       grantee    AS beneficiari, 
       owner      AS propietari_objecte, 
       table_name AS nom_objecte, 
       grantable  AS delegable, 
       hierarchy  AS jerarquia
FROM dba_tab_privs 
WHERE grantee LIKE ('%{username}%')
  AND grantor NOT LIKE ('%{username}%')
ORDER BY otorgant, privilegi;
```
### 14. llista els privilegis de sistema globals (com CREATE TABLE o DBA) assignats directament a l'usuari i si té permisos per concedir-los a altres.

```sql
SELECT grantee      AS beneficiari, 
       privilege    AS privilegi, 
       admin_option AS opcio_administrador, 
       common       AS comu, 
       inherited    AS heretat
FROM dba_sys_privs 
WHERE grantee LIKE ('%{username}%')
ORDER BY privilegi;

```

### 15. mostra els rols (conjunts de permisos) assignats a l'usuari i especifica si estan actius per defecte o si es poden heretar.

```sql
SELECT grantee       AS beneficiari, 
       granted_role  AS rol_assignat, 
       admin_option  AS opcio_administrador, 
       default_role  AS rol_per_defecte, 
       common        AS comu, 
       inherited     AS heretat
FROM dba_role_privs 
WHERE grantee LIKE ('%{username}%')
ORDER BY rol_assignat;
```
### 16. detalla l'estat, l'historial d'errors i la darrera activitat de les tasques programades (Jobs) propietat de l'usuari per verificar-ne el correcte funcionament.

```sql
WITH owners AS (
  SELECT username AS owner
  FROM dba_users
  WHERE username LIKE '%{username}%'
),
jobs AS (
  SELECT /*+ MATERIALIZE */ j.*
  FROM   dba_scheduler_jobs j
  JOIN   owners o ON o.owner = j.owner
)
SELECT 
    owner                                        AS propietari,
    job_name                                     AS nom_tasca,
    job_type                                     AS tipus_tasca,
    job_action                                   AS accio_tasca,
    enabled                                      AS habilitat,
    state                                        AS estat,
    run_count                                    AS total_execucions,
    failure_count                                AS total_errors,
    CAST(SYS_EXTRACT_UTC(last_start_date) AS DATE) AS inici_ultima_execucio_utc,
    TO_CHAR(CAST(SYS_EXTRACT_UTC(last_start_date) AS DATE),'YYYY-MM-DD HH24:MI:SS') AS inici_ultima_execucio_str,
    TO_CHAR(last_run_duration)                   AS durada_ultima_execucio,
    CAST(SYS_EXTRACT_UTC(next_run_date) AS DATE)   AS propera_execucio_utc
FROM jobs
ORDER BY inici_ultima_execucio_utc DESC NULLS LAST;

```
### 17. resumeix el rendiment i la taxa d'èxit de les tasques programades durant els darrers sis mesos per identificar quines fallen amb freqüència.

```sql
SELECT owner                                                 AS propietari, 
       job_name                                              AS nom_tasca, 
       COUNT(*)                                              AS total_execucions,
       MAX(log_date)                                         AS ultima_execucio,
       SUM(CASE WHEN status = 'SUCCEEDED' THEN 1 ELSE 0 END) AS execucions_correctes,
       SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END)    AS execucions_fallides
FROM dba_scheduler_job_log 
WHERE owner LIKE '%{username}%'
  AND log_date >= SYSDATE - 180
GROUP BY owner, job_name
ORDER BY ultima_execucio DESC;
```
### 18. llista les tasques programades de l'estil antic per comprovar-ne el codi, la propera execució i si han estat marcades com a defectuoses per excés d'errors.

```sql
SELECT job         AS id_tasca, 
       what        AS codi_execucio, 
       last_date   AS data_ultima_execucio, 
       last_sec    AS hora_ultima_execucio, 
       next_date   AS data_propera_execucio, 
       next_sec    AS hora_propera_execucio, 
       failures    AS errors_acumulats, 
       broken      AS aturada
FROM dba_jobs 
WHERE schema_user LIKE ('%{username}%')
```
#### 19. identifica les aplicacions d'Oracle APEX vinculades a l'usuari, mostrant-ne el volum de pàgines, l'estat de disponibilitat i quant de temps fa que no es modifiquen.

```sql
SELECT workspace                           AS espai_de_treball, 
       application_id                      AS id_aplicacio, 
       application_name                    AS nom_aplicacio, 
       owner                               AS propietari, 
       last_updated_on                     AS ultima_actualitzacio, 
       last_updated_by                     AS actualitzat_per, 
       pages                               AS pagines,
       ROUND(SYSDATE - last_updated_on, 0) AS dies_des_de_l_actualitzacio,
       application_group                   AS grup_aplicacio, 
       availability_status                 AS estat_disponibilitat
FROM apex_applications 
WHERE owner LIKE ('%{username}%')
ORDER BY last_updated_on DESC;
```
### 20. Obté l'última activitat de cada usuari a les aplicacions APEX del propietari, mostrant quina pàgina han visitat recentment i el seu volum total d'interaccions.

```sql
WITH base AS (
  SELECT a.*
  FROM apex_workspace_activity_log a
  WHERE a.view_timestamp >= SYSDATE - 180
    AND a.application_id IN (
      SELECT application_id
      FROM apex_applications
      WHERE owner LIKE '%{username}%'
    )
),
ranked AS (
  SELECT
    b.workspace,
    b.application_id,
    b.application_name,
    b.application_schema_owner,
    b.apex_user,
    b.view_timestamp,
    b.page_id,
    b.page_name,
    b.apex_session_id,
    b.ip_address,
    ROW_NUMBER() OVER (
      PARTITION BY b.application_id, b.apex_user
      ORDER BY b.view_timestamp DESC
    ) AS rn,
    COUNT(*) OVER (
      PARTITION BY b.application_id, b.apex_user
    ) AS num_hits
  FROM base b
)
SELECT
  workspace                AS espai_de_treball,
  application_id           AS id_aplicacio,
  application_name         AS nom_aplicacio,
  application_schema_owner AS propietari_esquema,
  apex_user                AS usuari_apex,
  view_timestamp           AS ultima_visita,
  page_id                  AS id_pagina,
  page_name                AS nom_pagina,
  apex_session_id          AS id_sessio_apex,
  ip_address               AS adreca_ip,
  num_hits                 AS total_clics
FROM ranked
WHERE rn = 1
ORDER BY ultima_visita DESC;
```
### 21. identifica les connexions externes (Database Links) configurades per l'usuari o de caràcter públic, detallant cap a quin servidor i usuari remot apunten.

```sql
SELECT owner    AS propietari, 
       db_link  AS nom_enllac_bd, 
       username AS usuari_remot, 
       host     AS host_remot, 
       created  AS data_creacio
FROM dba_db_links 
WHERE owner LIKE ('%{username}%')
   OR owner = 'PUBLIC' 
ORDER BY propietari, nom_enllac_bd;
```
### 22. identifica els disparadors (triggers) que contenen condicions lògiques específiques (WHEN), detallant sobre quines taules actuen i quin esdeveniment els activa.

```sql
SELECT owner            AS propietari, 
       trigger_name     AS nom_disparador, 
       trigger_type     AS tipus_disparador, 
       triggering_event AS esdeveniment_disparador,
       table_owner      AS propietari_taula, 
       table_name       AS nom_taula, 
       status           AS estat, 
       when_clause      AS clausula_condicional
FROM dba_triggers 
WHERE when_clause IS NOT NULL 
  AND (owner LIKE '%{username}%' OR table_owner LIKE '%{username}%')
ORDER BY propietari, nom_disparador;
```
### 23. llista tots els disparadors (triggers) actius de l'usuari, classificant-los segons si actuen a nivell de taula o de base de dades i detallant quin esdeveniment els executa.

```sql
SELECT
  owner                                                               AS propietari,
  trigger_name                                                        AS nom_disparador,
  status                                                              AS estat,
  trigger_type                                                        AS tipus_disparador, 
  triggering_event                                                    AS esdeveniment_disparador,
  table_owner                                                         AS propietari_taula,
  table_name                                                          AS nom_taula,
  CASE WHEN table_owner IS NULL THEN 'ESQUEMA/BD' ELSE 'TAULA/VISTA' END AS ambit,
  CASE WHEN when_clause IS NOT NULL THEN 'SÍ' ELSE 'NO' END           AS te_condicio_when
FROM dba_triggers
WHERE owner LIKE ('%{username}%')
  AND status = 'ENABLED'                         
ORDER BY propietari, ambit, propietari_taula NULLS LAST, nom_taula NULLS LAST, nom_disparador;
```

### 24. recupera l'historial d'execució de sentències SQL dels darrers 90 dies per a un usuari concret, permetent analitzar quines consultes ha llançat i amb quina freqüència.

```sql
SELECT *
FROM (
  SELECT
    s.end_interval_time                   AS data_snapshot,
    DBMS_LOB.SUBSTR(t.sql_text, 4000, 1)  AS text_sql,
    h.executions_delta                    AS execucions,
    h.parsing_schema_name                 AS esquema_execucio,
    NVL(h.module,'-')                     AS modul
  FROM dba_hist_sqlstat h
  JOIN dba_hist_snapshot s
    ON s.snap_id = h.snap_id
   AND s.dbid = h.dbid
   AND s.instance_number = h.instance_number
  JOIN dba_hist_sqltext t
    ON t.sql_id = h.sql_id
   AND t.dbid  = h.dbid
  WHERE h.parsing_schema_name LIKE '%{username}%'
    AND s.end_interval_time >= SYSDATE - 90
    AND h.executions_delta >= 1
  ORDER BY s.end_interval_time DESC
)
WHERE ROWNUM <= 500000
ORDER BY data_snapshot DESC;
```

### 25.  localitza qualsevol referència textual als esquemes indicats dins del codi font (procediments, funcions, triggers) d'altres usuaris per evitar ruptures de codi.

```sql
SELECT owner AS propietari, 
       name  AS nom_objecte, 
       type  AS tipus_objecte, 
       line  AS num_linia, 
       text  AS codi_font
FROM dba_source 
WHERE owner NOT IN ('SYS', 'SYSTEM', 'DBA', 'OUTLN', 'XDB') -- Exclou sistemes
  AND owner NOT LIKE '%{username}%'                        -- Exclou el propi grup d'esquemes
  AND UPPER(text) LIKE '%{username}%'                      -- Cerca la referència al codi
ORDER BY propietari, nom_objecte, num_linia;
```

### 26. localitza vistes de tercers que fan referència als esquemes indicats en la seva definició, evitant que aquestes vistes deixin de funcionar si s'eliminen els esquemes.

```sql
SELECT owner       AS propietari, 
       view_name   AS nom_vista, 
       text_length AS longitud_text, 
       text_vc     AS definicio_vlc
FROM dba_views 
WHERE owner NOT IN ('SYS', 'SYSTEM', 'XDB', 'APEX_200200')
  AND owner NOT LIKE '%{username}%'
  AND UPPER(text_vc) LIKE '%{username}%'
ORDER BY propietari, nom_vista;
```
### 3. Aquesta consulta extrau la configuració tècnica, l'estat de seguretat i l'historial de connexió d'usuaris específics a la base de dades Oracle.

```
### A. Resum i Dimensionament
Recupera l'estat del compte, la mida total en GB i la data de creació.
```sql
SELECT u.username, u.account_status, ROUND(SYSDATE - u.created, 0) as days_old,
    (SELECT ROUND(SUM(bytes)/1024/1024/1024,3) FROM dba_segments WHERE owner = '{username}') as size_gb,
    (SELECT COUNT(*) FROM dba_objects WHERE owner = '{username}') as object_count,
    (SELECT ROUND(SYSDATE - CAST(last_login AS DATE), 0) FROM dba_users WHERE username = '{username}') as last_login_days_ago
FROM dba_users u WHERE u.username = '{username}'
```
### 2. Calcula la mida total en GB que ocupa cada esquema a la base de dades i el nombre de segments que té.
```sql
SELECT
  owner                                             AS "esquema",
  ROUND(SUM(bytes)/1024/1024/1024,2)                AS "mida (GB)",
  COUNT(*)                                          AS "nombre de segments"
FROM dba_segments
WHERE owner LIKE '%{username}%'
GROUP BY owner;
```
### B. Activitat de Dades (DML)
Analitza si hi ha hagut insercions, actualitzacions o eliminacions recents.
```sql
SELECT table_name, inserts, updates, deletes, timestamp 
FROM dba_tab_modifications 
WHERE table_owner = '{username}' 
ORDER BY timestamp DESC 
FETCH FIRST 10 ROWS ONLY
```

### C. Estadístiques Recents
S'utilitza com a indicador d'activitat si no hi ha logs DML actius.
```sql
SELECT table_name, num_rows, last_analyzed, ROUND(SYSDATE - last_analyzed, 0) as days_since_stats 
FROM dba_tables 
WHERE owner = '{username}' AND last_analyzed IS NOT NULL 
ORDER BY last_analyzed DESC 
FETCH FIRST 5 ROWS ONLY
```

### D. Cerca Exhaustiva de Dependències (Wildcard Search)
Aquesta és la part més crítica per evitar falsos positius. Se cerca la cadena `'%{username}.%'` a tot el codi i vistes de la base de dades.

1. **En Codi Font (`dba_source`):**
```sql
SELECT owner, name, type FROM dba_source 
WHERE (UPPER(text) LIKE '%{username}.%') 
AND owner NOT IN ('SYS','SYSTEM','{username}')
```

2. **En Definicions de Vistes (`dba_views`):**
```sql
SELECT owner, view_name FROM dba_views 
WHERE (UPPER(text_vc) LIKE '%{username}.%') 
AND owner NOT IN ('SYS','SYSTEM','{username}')
```

3. **En Triggers (`dba_triggers`):**
```sql
SELECT owner, trigger_name FROM dba_triggers 
WHERE (UPPER(when_clause) LIKE '%{username}.%') 
AND owner NOT IN ('SYS','SYSTEM','{username}')
```

### E. Infraestructura i Valor
Detecta si l'esquema suportat aplicacions APEX o té automatismes lligats.
```sql
-- Apps APEX
SELECT application_id, application_name FROM apex_applications WHERE owner = '{username}'

-- Jobs Scheduler
SELECT job_name, enabled, state FROM dba_scheduler_jobs WHERE owner = '{username}'

-- Database Links
SELECT db_link, host FROM dba_db_links WHERE owner = '{username}' OR owner = 'PUBLIC'
```

## 3. Algorisme de Puntuació (v3.2)

La nota final és una suma de factors de risc (max 100) que es redueix dràsticament mitjançant **Bonificadors de Seguretat**.

### Factors de Risc (Suma)
- **Activitat nul·la**: +30 pts (si no hi ha DML ni stats < 60 dies).
- **Aïllament total**: +30 pts (si no es troben refs en codi ni dependències).
- **Inactivitat Humana**: +10 pts (si darrer login > 180 dies).
- **Mida irrellevant**: +15 pts (si ocupa < 50MB).
- **Poc valor executiu**: +15 pts (si no té Jobs ni APEX).

### Bonificadors de "Salvatge" (Resta)
- **Referència en Codi Extern**: **-40 pts** (Es considera sota ús encara que estigui "estàtic").
- **App APEX Detectada**: **Reducció al 50% de la nota final**.
- **Dependència Formal**: **-20 pts** (Refs a `dba_dependencies` o sinònims).

---
*Aquest motor garanteix que un esquema que tingui codi que el crida mai arribarà al 100% de risc, actuant com una barrera de seguretat abans de qualsevol proposta de borrat.*
