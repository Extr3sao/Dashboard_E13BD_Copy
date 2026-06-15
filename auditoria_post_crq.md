# Auditoria tècnica post-CRQ / desenvolupaments recents

## Descripció

Detecta males pràctiques de disseny i desenvolupament en objectes Oracle modificats recentment, amb focus en canvis de CRQ / desplegaments.

## Abast

- Esquemes no de sistema
- Objectes modificats en els últims `N` dies

## Notes

- Aquest enfocament serveix per auditar canvis **DDL** / desplegaments recents.
- No pretén mesurar activitat **DML** (`INSERT / UPDATE / DELETE`).
- Totes les columnes de sortida estan etiquetades en **català**.

## Paràmetre comú

```sql
DEFINE DAYS_BACK = 7;
```

---

```sql
-- =============================================================================
-- CHECK 01: TAULES RECENTS SENSE PRIMARY KEY
-- Criteri:
--   Identifica taules d'usuari modificades recentment que no tenen clau
--   primària habilitada.
-- =============================================================================
WITH esquemes_valids AS (
    SELECT u.username AS owner
    FROM dba_users u
    WHERE u.oracle_maintained = 'N'
      AND u.username NOT IN (
          'SYS','SYSTEM','DBSNMP','SYSMAN','ORACLE_OCM','OUTLN','WMSYS','XDB',
          'OLAPSYS','MDSYS','CTXSYS','EXFSYS','ORDSYS','ORDPLUGINS','DMSYS',
          'OJVMSYS','AUDSYS','LBACSYS','GSMADMIN_INTERNAL','ANONYMOUS','DIP',
          'APPQOSSYS','ORDDATA','SI_INFORMTN_SCHEMA','SYSKM','SYSBACKUP',
          'SYSDG','SYSRAC','AUSYS','DBSFWUSER','REMOTE_SCHEDULER_AGENT',
          'MDDATA','OWBSYS','OWBSYS_AUDIT','FLOWS_FILES','APEX_PUBLIC_USER',
          'XS$NULL','SPATIAL_CSW_ADMIN_USR','SPATIAL_WFS_ADMIN_USR',
          'MGMT_VIEW','PDBADMIN','DVSYS','DVF','GGSYS','SYSAUX'
      )
      AND u.username NOT LIKE 'APEX_%'
      AND u.username NOT LIKE 'FLOWS_%'
      AND u.username NOT LIKE 'ORDS%'
      AND u.username NOT LIKE 'ORACLE_%'
),
esquemes_actius AS (
    SELECT DISTINCT o.owner
    FROM dba_objects o
    JOIN esquemes_valids ev ON ev.owner = o.owner
    WHERE o.last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS')
                              AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
)
SELECT
    t.owner                                       AS esquema,
    t.table_name                                  AS taula,
    NVL(TO_CHAR(t.num_rows), 'sense estadistiques') AS num_rows,
    NVL(TO_CHAR(t.last_analyzed, 'YYYY-MM-DD'), 'mai') AS darrera_estadistica,
    TO_CHAR(o.last_ddl_time, 'YYYY-MM-DD HH24:MI') AS data_modificacio_objecte
FROM dba_tables t
JOIN dba_objects o
  ON o.owner = t.owner AND o.object_name = t.table_name AND o.object_type = 'TABLE'
WHERE t.owner IN (SELECT owner FROM esquemes_actius)
  AND t.temporary = 'N'
  AND t.iot_type IS NULL
  AND UPPER(t.table_name) NOT LIKE '%TMP%'
  AND NVL(t.num_rows, -1) <> 0
  AND o.last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS')
                          AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
  AND NOT EXISTS (
      SELECT 1
      FROM dba_constraints c
      WHERE c.owner = t.owner
        AND c.table_name = t.table_name
        AND c.constraint_type = 'P'
        AND c.status = 'ENABLED'
  )
ORDER BY t.owner, t.table_name;
```

---

```sql
-- =============================================================================
-- CHECK 02: TAULES RECENTS SENSE ÍNDEXS
-- Severitat: ALT
-- Criteri:
--   Identifica taules d'usuari modificades recentment sense cap índex, excloent
--   esquemes de sistema i taules temporals.
-- =============================================================================

WITH esquemes_actius AS (
    SELECT DISTINCT o.owner
    FROM dba_objects o
    WHERE o.last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS')
                              AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
      AND o.owner NOT IN ('SYS','SYSTEM','DBSNMP','SYSMAN','ORACLE_OCM','OUTLN','WMSYS','XDB','OLAPSYS','MDSYS','CTXSYS','EXFSYS','ORDSYS','ORDPLUGINS','DMSYS','OJVMSYS','AUDSYS','LBACSYS','GSMADMIN_INTERNAL','ANONYMOUS','DIP','APPQOSSYS','ORDDATA','SI_INFORMTN_SCHEMA','SYSKM','SYSBACKUP','SYSDG','SYSRAC','AUSYS','DBSFWUSER','REMOTE_SCHEDULER_AGENT','MDDATA','OWBSYS','OWBSYS_AUDIT','FLOWS_FILES','APEX_PUBLIC_USER','XS$NULL','SPATIAL_CSW_ADMIN_USR','SPATIAL_WFS_ADMIN_USR','MGMT_VIEW','PDBADMIN','DVSYS','DVF','GGSYS','SYSAUX')
      AND o.owner NOT LIKE 'APEX_%' AND o.owner NOT LIKE 'FLOWS_%' AND o.owner NOT LIKE 'ORDS%' AND o.owner NOT LIKE 'ORACLE_%'
)
SELECT
    t.owner                                              AS esquema,
    t.table_name                                         AS taula,
    NVL(TO_CHAR(t.num_rows), 'sense estadistiques')      AS num_rows,
    NVL(TO_CHAR(t.last_analyzed, 'YYYY-MM-DD'), 'mai')   AS darrera_estadistica,
    TO_CHAR(o.last_ddl_time, 'YYYY-MM-DD HH24:MI')       AS data_modificacio_objecte
FROM dba_tables t
JOIN dba_objects o
  ON o.owner = t.owner AND o.object_name = t.table_name AND o.object_type = 'TABLE'
WHERE t.owner IN (SELECT owner FROM esquemes_actius)
  AND t.temporary = 'N'
  AND t.iot_type IS NULL
  AND UPPER(t.table_name) NOT LIKE '%TMP%'
  AND UPPER(t.table_name) NOT LIKE '%APEX%'
  AND NVL(t.num_rows, -1) <> 0
  AND o.last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS')
                          AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
  AND NOT EXISTS (
      SELECT 1
      FROM dba_indexes i
      WHERE i.table_owner = t.owner AND i.table_name = t.table_name
  )
ORDER BY t.owner, t.table_name;
```

---

```sql
-- =============================================================================
-- CHECK 03: SEQÜÈNCIES SENSE CACHE
-- Severitat: MITJÀ
-- Criteri:
--   Detecta seqüències modificades recentment amb NOCACHE o cache < 20 en
--   esquemes d'aplicació.
-- =============================================================================

SELECT
    s.sequence_owner                                           AS esquema,
    s.sequence_name                                            AS sequencia,
    TO_CHAR(s.cache_size)                                      AS cache_actual,
    TO_CHAR(s.increment_by)                                    AS incr_by,
    CASE WHEN s.cache_size = 0 THEN 'NOCACHE' ELSE 'Cache insuficient (<20)' END AS problema,
    'N/D (Sense permís AWR)'                                   AS avg_nextval_dia,
    '-'                                                        AS pic_max_snapshot,
    TO_CHAR(CASE
        WHEN s.cache_size = 0 AND s.increment_by = 1 THEN 50
        WHEN s.cache_size = 0 AND s.increment_by > 1 THEN 100
        ELSE 20
    END) AS cache_recomanada,
    CASE
        WHEN s.cache_size = 0 AND s.increment_by = 1 THEN 'NOCACHE + increment=1 (OLTP): minim 50'
        WHEN s.cache_size = 0 AND s.increment_by > 1 THEN 'NOCACHE + increment>1 (Batch): recomanat 100'
        ELSE 'Cache < 20: insuficient, minim recomanat 20'
    END AS justificacio,
    'Heuristica'                                               AS font_dades,
    TO_CHAR(o.last_ddl_time, 'YYYY-MM-DD HH24:MI')             AS data_modificacio_objecte
FROM dba_sequences s
JOIN dba_objects o
  ON o.owner = s.sequence_owner AND o.object_name = s.sequence_name AND o.object_type = 'SEQUENCE'
WHERE s.sequence_owner IN (
    SELECT DISTINCT owner FROM dba_objects
    WHERE last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS') 
                            AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
      AND owner NOT IN ('SYS','SYSTEM','DBSNMP','SYSMAN','ORACLE_OCM','OUTLN','WMSYS','XDB','OLAPSYS','MDSYS','CTXSYS','EXFSYS','ORDSYS','ORDPLUGINS','DMSYS','OJVMSYS','AUDSYS','LBACSYS','GSMADMIN_INTERNAL','ANONYMOUS','DIP','APPQOSSYS','ORDDATA','SI_INFORMTN_SCHEMA','SYSKM','SYSBACKUP','SYSDG','SYSRAC','AUSYS','DBSFWUSER','REMOTE_SCHEDULER_AGENT','MDDATA','OWBSYS','OWBSYS_AUDIT','FLOWS_FILES','APEX_PUBLIC_USER','XS$NULL','SPATIAL_CSW_ADMIN_USR','SPATIAL_WFS_ADMIN_USR','MGMT_VIEW','PDBADMIN','DVSYS','DVF','GGSYS','SYSAUX')
)
  AND s.cache_size < 20
  AND o.last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS') 
                          AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
ORDER BY s.sequence_owner, s.sequence_name;
```

---

```sql
-- =============================================================================
-- CHECK 04: FOREIGN KEYS SENSE ÍNDEX DE SUPORT
-- Severitat: ALT
-- Criteri:
--   Detecta claus foranes que no disposen d índex sobre la seva primera
--   columna.   Aquesta situació pot provocar bloquejos de taula durant
--   DELETE/UPDATE.   És relevant per evitar interrupcions en operacions
-- =============================================================================
WITH esquemes_actius AS (
    SELECT DISTINCT owner 
    FROM dba_objects
    WHERE last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS') 
                            AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
      AND owner NOT IN ('SYS','SYSTEM','DBSNMP','SYSMAN','ORACLE_OCM','OUTLN','WMSYS','XDB','OLAPSYS','MDSYS','CTXSYS','EXFSYS','ORDSYS','ORDPLUGINS','DMSYS','OJVMSYS','AUDSYS','LBACSYS','GSMADMIN_INTERNAL','ANONYMOUS','DIP','APPQOSSYS','ORDDATA','SI_INFORMTN_SCHEMA','SYSKM','SYSBACKUP','SYSDG','SYSRAC','AUSYS','DBSFWUSER','REMOTE_SCHEDULER_AGENT','MDDATA','OWBSYS','OWBSYS_AUDIT','FLOWS_FILES','APEX_PUBLIC_USER','XS$NULL','SPATIAL_CSW_ADMIN_USR','SPATIAL_WFS_ADMIN_USR','MGMT_VIEW','PDBADMIN','DVSYS','DVF','GGSYS','SYSAUX')
      AND owner NOT LIKE 'APEX_%' AND owner NOT LIKE 'FLOWS_%' AND owner NOT LIKE 'ORDS%' AND owner NOT LIKE 'ORACLE_%'
)
SELECT DISTINCT
    c.owner AS esquema,
    c.table_name AS taula,
    c.constraint_name AS constraint_fk,
    (SELECT LISTAGG(cc2.column_name, ', ') WITHIN GROUP (ORDER BY cc2.position)
       FROM dba_cons_columns cc2
      WHERE cc2.owner = c.owner AND cc2.constraint_name = c.constraint_name) AS columnes_fk,
    r.owner || '.' || r.table_name AS taula_pare,
    TO_CHAR(o.last_ddl_time, 'YYYY-MM-DD HH24:MI') AS data_modificacio_taula
FROM dba_constraints c
JOIN dba_cons_columns cc
  ON c.owner = cc.owner AND c.constraint_name = cc.constraint_name AND cc.position = 1 
JOIN dba_constraints r
  ON c.r_owner = r.owner AND c.r_constraint_name = r.constraint_name 
JOIN dba_objects o
  ON o.owner = c.owner AND o.object_name = c.table_name AND o.object_type = 'TABLE'
WHERE c.owner IN (SELECT owner FROM esquemes_actius)
  AND c.constraint_type = 'R' 
  AND c.status = 'ENABLED'
  AND UPPER(c.table_name) NOT LIKE '%TMP%'
  AND UPPER(c.table_name) NOT LIKE '%APEX%'
  AND o.last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS') AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
  AND NOT EXISTS (
      SELECT 1
      FROM dba_ind_columns ic
      WHERE ic.table_owner = c.owner AND ic.table_name = c.table_name
        AND ic.column_name = cc.column_name AND ic.column_position = 1
  )
ORDER BY c.owner, c.table_name, c.constraint_name;
```

---

```sql
-- =============================================================================
-- CHECK 05: CONSTRAINTS RECENTS DESHABILITADES
-- Severitat: Crític
-- Criteri:
--   Detecta constraints deshabilitades en taules modificades recentment,
--   excloent esquemes del sistema i taules temporals.
-- Riesgo   : Integridad referencial y de unicidad no garantizada en runtime.
-- Filtros  : sin TMP en nombre de tabla, num_rows != 0
-- =============================================================================


WITH esquemes_actius AS (
    -- Filtramos los esquemas que han tenido actividad y aplicamos exclusiones
    SELECT DISTINCT owner 
    FROM dba_objects
    WHERE last_ddl_time BETWEEN TO_DATE(&START_AT, 'YYYY-MM-DD HH24:MI:SS') 
                            AND TO_DATE(&END_AT, 'YYYY-MM-DD HH24:MI:SS')
      AND owner NOT IN (
          'SYS','SYSTEM','DBSNMP','SYSMAN','ORACLE_OCM','OUTLN','WMSYS','XDB',
          'OLAPSYS','MDSYS','CTXSYS','EXFSYS','ORDSYS','ORDPLUGINS','DMSYS',
          'OJVMSYS','AUDSYS','LBACSYS','GSMADMIN_INTERNAL','ANONYMOUS','DIP',
          'APPQOSSYS','ORDDATA','SI_INFORMTN_SCHEMA','SYSKM','SYSBACKUP',
          'SYSDG','SYSRAC','AUSYS','DBSFWUSER','REMOTE_SCHEDULER_AGENT',
          'MDDATA','OWBSYS','OWBSYS_AUDIT','FLOWS_FILES','APEX_PUBLIC_USER',
          'XS$NULL','SPATIAL_CSW_ADMIN_USR','SPATIAL_WFS_ADMIN_USR',
          'MGMT_VIEW','PDBADMIN','DVSYS','DVF','GGSYS','SYSAUX'
      )
      AND owner NOT LIKE 'APEX_%' 
      AND owner NOT LIKE 'FLOWS_%'
      AND owner NOT LIKE 'ORDS%'  
      AND owner NOT LIKE 'ORACLE_%'
)
SELECT
    ac.owner AS esquema,
    ac.table_name AS taula,
    ac.constraint_name AS nom_constraint,
    CASE ac.constraint_type
        WHEN 'P' THEN 'PRIMARY KEY'
        WHEN 'U' THEN 'UNIQUE'
        WHEN 'R' THEN 'FOREIGN KEY'
        WHEN 'C' THEN 'CHECK'
        ELSE ac.constraint_type
    END AS tipus_constraint,
    ac.status AS estat,
    ac.validated AS validada,
    TO_CHAR(o.last_ddl_time, 'YYYY-MM-DD HH24:MI') AS data_modificacio_taula
FROM all_constraints ac
JOIN dba_objects o
  ON o.owner = ac.owner
 AND o.object_name = ac.table_name
 AND o.object_type = 'TABLE'
WHERE ac.owner IN (SELECT owner FROM esquemes_actius)
  AND ac.status = 'DISABLED' 
  AND ac.constraint_type IN ('P', 'U', 'R', 'C')
  -- Filtre per evitar taules temporals o de treball
  AND UPPER(ac.table_name) NOT LIKE '%TMP%'
  -- Filtre de data sobre la taula
  AND o.last_ddl_time BETWEEN TO_DATE(&START_AT, 'YYYY-MM-DD HH24:MI:SS') 
                          AND TO_DATE(&END_AT, 'YYYY-MM-DD HH24:MI:SS')
ORDER BY ac.owner, ac.table_name, ac.constraint_type, ac.constraint_name;
```

---

```sql
-- =============================================================================
-- CHECK 06: ÍNDEXS DUPLICATS RECENTS (MATEIXA COLUMNA LÍDER)
-- Severitat: BAIX
-- Criteri:
--   Detecta parelles d'índexs sobre la mateixa taula que comparteixen la
--   columna líder i que s'han modificat recentment, indicant possibles
--   redundàncies.
-- =============================================================================

WITH esquemes_actius AS (
    SELECT DISTINCT owner 
    FROM dba_objects
    WHERE last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS') 
                            AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
      AND owner NOT IN ('SYS','SYSTEM','DBSNMP','SYSMAN','ORACLE_OCM','OUTLN','WMSYS','XDB','OLAPSYS','MDSYS','CTXSYS','EXFSYS','ORDSYS','ORDPLUGINS','DMSYS','OJVMSYS','AUDSYS','LBACSYS','GSMADMIN_INTERNAL','ANONYMOUS','DIP','APPQOSSYS','ORDDATA','SI_INFORMTN_SCHEMA','SYSKM','SYSBACKUP','SYSDG','SYSRAC','AUSYS','DBSFWUSER','REMOTE_SCHEDULER_AGENT','MDDATA','OWBSYS','OWBSYS_AUDIT','FLOWS_FILES','APEX_PUBLIC_USER','XS$NULL','SPATIAL_CSW_ADMIN_USR','SPATIAL_WFS_ADMIN_USR','MGMT_VIEW','PDBADMIN','DVSYS','DVF','GGSYS','SYSAUX')
      AND owner NOT LIKE 'APEX_%' AND owner NOT LIKE 'FLOWS_%' AND owner NOT LIKE 'ORDS%' AND owner NOT LIKE 'ORACLE_%'
),
indices_candidats AS (
    SELECT 
        i.owner, 
        i.table_name, 
        i.index_name, 
        i.index_type, 
        ic.column_name, 
        o.last_ddl_time
    FROM dba_indexes i
    JOIN dba_ind_columns ic ON i.owner = ic.index_owner AND i.index_name = ic.index_name
    JOIN dba_objects o ON i.owner = o.owner AND i.index_name = o.object_name
    WHERE i.owner IN (SELECT owner FROM esquemes_actius)
      AND ic.column_position = 1
      AND o.object_type = 'INDEX'
      AND UPPER(i.table_name) NOT LIKE '%TMP%'
      AND UPPER(i.table_name) NOT LIKE '%APEX%'
)
SELECT DISTINCT
    idx1.owner AS esquema,
    idx1.table_name AS taula,
    idx1.index_name AS index_1,
    idx2.index_name AS index_2,
    idx1.column_name AS columna_lider_comuna,
    idx1.index_type AS tipus_1,
    idx2.index_type AS tipus_2,
    TO_CHAR(GREATEST(idx1.last_ddl_time, idx2.last_ddl_time), 'YYYY-MM-DD HH24:MI') AS data_modificacio_mes_recent
FROM indices_candidats idx1
JOIN indices_candidats idx2
  ON idx1.owner = idx2.owner AND idx1.table_name = idx2.table_name AND idx1.column_name = idx2.column_name 
 AND idx1.index_name < idx2.index_name  
WHERE (idx1.last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS') AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
       OR 
       idx2.last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS') AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS'))
ORDER BY idx1.owner, idx1.table_name, idx1.index_name;
```

---

```sql
-- =============================================================================
-- CHECK 07: OBJECTES RECENTS INVÀLIDS
-- Severitat: CRÍTIC
-- Criteri:
--   Detecta objectes d'usuari invàlids modificats en els últims N dies.
-- =============================================================================

SELECT
    owner AS esquema,
    object_name AS objecte,
    object_type AS tipus_objecte,
    TO_CHAR(created, 'YYYY-MM-DD') AS data_creacio,
    TO_CHAR(last_ddl_time, 'YYYY-MM-DD HH24:MI:SS') AS data_invalidacio
FROM dba_objects
WHERE status = 'INVALID'
  AND last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS') AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
  AND owner NOT IN ('SYS','SYSTEM','DBSNMP','SYSMAN','ORACLE_OCM','OUTLN','WMSYS','XDB','OLAPSYS','MDSYS','CTXSYS','EXFSYS','ORDSYS','ORDPLUGINS','DMSYS','OJVMSYS','AUDSYS','LBACSYS','GSMADMIN_INTERNAL','ANONYMOUS','DIP','APPQOSSYS','ORDDATA','SI_INFORMTN_SCHEMA','SYSKM','SYSBACKUP','SYSDG','SYSRAC','AUSYS','DBSFWUSER','REMOTE_SCHEDULER_AGENT','MDDATA','OWBSYS','OWBSYS_AUDIT','FLOWS_FILES','APEX_PUBLIC_USER','XS$NULL','SPATIAL_CSW_ADMIN_USR','SPATIAL_WFS_ADMIN_USR','MGMT_VIEW','PDBADMIN','DVSYS','DVF','GGSYS','SYSAUX')
  AND owner NOT LIKE 'APEX_%' AND owner NOT LIKE 'FLOWS_%' AND owner NOT LIKE 'ORDS%' AND owner NOT LIKE 'ORACLE_%'
  AND UPPER(object_name) NOT LIKE '%TMP%'
  AND UPPER(object_name) NOT LIKE '%APEX%'
ORDER BY owner, object_type, object_name;
```

---

```sql

-- =============================================================================
-- CHECK 08: COLUMNES NUMBER SENSE PRECISIÓ NI ESCALA
-- Severitat: MITJÀ
-- Criteri:
--   Identifica columnes NUMBER sense precisió/escala en taules modificades
--   recentment.
-- =============================================================================
SELECT
    tc.owner AS esquema,
    tc.table_name AS taula,
    tc.column_name AS columna,
    tc.nullable AS nullable,
    tc.column_id AS posicio,
    TO_CHAR(o.last_ddl_time, 'YYYY-MM-DD HH24:MI') AS data_modificacio_taula
FROM all_tab_columns tc
JOIN dba_objects o
  ON o.owner = tc.owner
 AND o.object_name = tc.table_name
 AND o.object_type = 'TABLE'
WHERE tc.data_type = 'NUMBER'
  AND tc.data_precision IS NULL
  AND tc.data_scale IS NULL
  -- Filtre de data directe sobre l'objecte taula
  AND o.last_ddl_time BETWEEN TO_DATE(&START_AT, 'YYYY-MM-DD HH24:MI:SS')
                          AND TO_DATE(&END_AT,   'YYYY-MM-DD HH24:MI:SS')
  -- Filtres d'exclusió d'esquemes (Llista negra)
  AND tc.owner NOT IN (
      'SYS','SYSTEM','DBSNMP','SYSMAN','ORACLE_OCM','OUTLN','WMSYS','XDB',
      'OLAPSYS','MDSYS','CTXSYS','EXFSYS','ORDSYS','ORDPLUGINS','DMSYS',
      'OJVMSYS','AUDSYS','LBACSYS','GSMADMIN_INTERNAL','ANONYMOUS','DIP',
      'APPQOSSYS','ORDDATA','SI_INFORMTN_SCHEMA','SYSKM','SYSBACKUP',
      'SYSDG','SYSRAC','AUSYS','DBSFWUSER','REMOTE_SCHEDULER_AGENT',
      'MDDATA','OWBSYS','OWBSYS_AUDIT','FLOWS_FILES','APEX_PUBLIC_USER',
      'XS$NULL','SPATIAL_CSW_ADMIN_USR','SPATIAL_WFS_ADMIN_USR',
      'MGMT_VIEW','PDBADMIN','DVSYS','DVF','GGSYS','SYSAUX'
  )
  AND tc.owner NOT LIKE 'APEX_%' 
  AND tc.owner NOT LIKE 'FLOWS_%'
  AND tc.owner NOT LIKE 'ORDS%' 
  AND tc.owner NOT LIKE 'ORACLE_%'
  -- Filtre de nom de taula
  AND UPPER(tc.table_name) NOT LIKE '%TMP%'
ORDER BY tc.owner, tc.table_name, tc.column_id
```

---

```sql
-- =============================================================================
-- CHECK 09: SINÒNIMS RECENTS TRENCATS
-- Severitat: BAIX
-- Criteri:
--   Detecta sinònims modificats recentment que apunten a objectes inexistents,
--   excloent DB_LINK i esquemes de sistema.
-- =============================================================================
SELECT
    s.owner AS esquema,
    s.synonym_name AS sinonim,
    s.table_owner AS propietari_desti,
    s.table_name AS objecte_desti,
    TO_CHAR(o.last_ddl_time, 'YYYY-MM-DD HH24:MI') AS data_modificacio_sinonim
FROM dba_synonyms s
JOIN dba_objects o
  ON o.owner = s.owner AND o.object_name = s.synonym_name AND o.object_type = 'SYNONYM'
WHERE s.db_link IS NULL
  AND o.last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS') AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
  AND s.owner NOT IN ('SYS','SYSTEM','DBSNMP','SYSMAN','ORACLE_OCM','OUTLN','WMSYS','XDB','OLAPSYS','MDSYS','CTXSYS','EXFSYS','ORDSYS','ORDPLUGINS','DMSYS','OJVMSYS','AUDSYS','LBACSYS','GSMADMIN_INTERNAL','ANONYMOUS','DIP','APPQOSSYS','ORDDATA','SI_INFORMTN_SCHEMA','SYSKM','SYSBACKUP','SYSDG','SYSRAC','AUSYS','DBSFWUSER','REMOTE_SCHEDULER_AGENT','MDDATA','OWBSYS','OWBSYS_AUDIT','FLOWS_FILES','APEX_PUBLIC_USER','XS$NULL','SPATIAL_CSW_ADMIN_USR','SPATIAL_WFS_ADMIN_USR','MGMT_VIEW','PDBADMIN','DVSYS','DVF','GGSYS','SYSAUX')
  AND s.owner NOT LIKE 'APEX_%' AND s.owner NOT LIKE 'FLOWS_%' AND s.owner NOT LIKE 'ORDS%' AND s.owner NOT LIKE 'ORACLE_%'
  AND NOT EXISTS (
      SELECT 1
      FROM dba_objects ao
      WHERE ao.owner = s.table_owner AND ao.object_name = s.table_name
  )
ORDER BY s.owner, s.synonym_name;
```

---

```sql
-- =============================================================================
-- CHECK 10: WHEN OTHERS THEN NULL EN CODI RECENT
-- Severitat: STOPPER
-- Criteri:
--   Detecta blocs de codi amb gestió d'errors genèrica 'WHEN OTHERS THEN NULL'
--   en objectes modificats recentment.   Aquest patró pot amagar omissió
--   d'maneig d'errors i risc de seguretat.
-- =============================================================================

SELECT
    s.owner AS esquema,
    s.name AS objecte,
    s.type AS tipus,
    s.line AS linia,
    SUBSTR(TRIM(s.text), 1, 200) AS codi,
    TO_CHAR(o.last_ddl_time, 'YYYY-MM-DD HH24:MI') AS data_modificacio_objecte
FROM all_source s
JOIN dba_objects o
  ON o.owner = s.owner
 AND o.object_name = s.name
 AND o.object_type = s.type
WHERE 
    -- 1. Filtre de data sobre l'objecte (Optimització: primer per data)
    o.last_ddl_time BETWEEN TO_DATE(&START_AT, 'YYYY-MM-DD HH24:MI:SS')
                        AND TO_DATE(&END_AT,   'YYYY-MM-DD HH24:MI:SS')
    
    -- 2. Filtre de contingut (Patró STOPPER)
    AND REGEXP_LIKE(s.text, 'WHEN\s+OTHERS\s+THEN\s+NULL', 'i')
    
    -- 3. Exclusió d'esquemes de sistema i eines
    AND s.owner NOT IN (
        'SYS','SYSTEM','DBSNMP','SYSMAN','ORACLE_OCM','OUTLN','WMSYS','XDB',
        'OLAPSYS','MDSYS','CTXSYS','EXFSYS','ORDSYS','ORDPLUGINS','DMSYS',
        'OJVMSYS','AUDSYS','LBACSYS','GSMADMIN_INTERNAL','ANONYMOUS','DIP',
        'APPQOSSYS','ORDDATA','SI_INFORMTN_SCHEMA','SYSKM','SYSBACKUP',
        'SYSDG','SYSRAC','AUSYS','DBSFWUSER','REMOTE_SCHEDULER_AGENT',
        'MDDATA','OWBSYS','OWBSYS_AUDIT','FLOWS_FILES','APEX_PUBLIC_USER',
        'XS$NULL','SPATIAL_CSW_ADMIN_USR','SPATIAL_WFS_ADMIN_USR',
        'MGMT_VIEW','PDBADMIN','DVSYS','DVF','GGSYS','SYSAUX'
    )
    AND s.owner NOT LIKE 'APEX_%' 
    AND s.owner NOT LIKE 'FLOWS_%'
    AND s.owner NOT LIKE 'ORDS%'  
    AND s.owner NOT LIKE 'ORACLE_%'
    
    -- 4. Només tipus d'objectes que contenen codi executable
    AND s.type IN ('PROCEDURE', 'FUNCTION', 'PACKAGE BODY', 'TRIGGER', 'TYPE BODY')
ORDER BY s.owner, s.name, s.line;
```

---

```sql
-- =============================================================================
-- CHECK 11: PROBLEMES DE CODI EN PAQUETS/PROCEDURES/FUNCIONS
-- Severitat: ALT
-- Criteri:
--   Detecta proximitat heurística entre sentències d'inici de bucle (LOOP,
--   FOR ... IN) i operacions DML (INSERT/UPDATE/DELETE/SELECT INTO) en un
--   radi de menys de 25 línies, en objectes PL/SQL modificats recentment
--   que no utilitzen BULK COLLECT ni FORALL.
-- Nota:
--   Aquesta SQL NO detecta DBMS_OUTPUT, EXECUTE IMMEDIATE ni COMMIT en bucle.
--   Per cobrir aquests patrons caldria afegir regex addicionals.
-- =============================================================================
WITH esquemes_valids AS (
    SELECT username AS owner
    FROM dba_users
    WHERE oracle_maintained = 'N'
      AND username NOT IN ('SYS','SYSTEM','DBSNMP','SYSMAN','ORACLE_OCM','OUTLN','WMSYS','XDB','OLAPSYS','MDSYS','CTXSYS','EXFSYS','ORDSYS','ORDPLUGINS','DMSYS','OJVMSYS','AUDSYS','LBACSYS','GSMADMIN_INTERNAL','ANONYMOUS','DIP','APPQOSSYS','ORDDATA','SI_INFORMTN_SCHEMA','SYSKM','SYSBACKUP','SYSDG','SYSRAC','AUSYS','DBSFWUSER','REMOTE_SCHEDULER_AGENT','MDDATA','OWBSYS','OWBSYS_AUDIT','FLOWS_FILES','APEX_PUBLIC_USER','XS$NULL','SPATIAL_CSW_ADMIN_USR','SPATIAL_WFS_ADMIN_USR','MGMT_VIEW','PDBADMIN','DVSYS','DVF','GGSYS','SYSAUX')
      AND username NOT LIKE 'APEX_%' AND username NOT LIKE 'FLOWS_%' AND username NOT LIKE 'ORDS%' AND username NOT LIKE 'ORACLE_%'
),
objectes_en_rang AS (
    SELECT owner, object_name, object_type, last_ddl_time
    FROM dba_objects
    WHERE last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS') AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
      AND object_type IN ('PROCEDURE', 'FUNCTION', 'PACKAGE BODY', 'TRIGGER')
      AND owner IN (SELECT owner FROM esquemes_valids)
),
linies_clau AS (
    SELECT s.owner, s.name, s.type, s.line, s.text,
        CASE 
            WHEN REGEXP_LIKE(s.text, '\bLOOP\b|FOR\s+\w+\s+IN\s*\(', 'i') THEN 'INICI_LOOP'
            WHEN REGEXP_LIKE(s.text, '\b(INSERT\s+INTO|UPDATE\s+\S+\s+SET|DELETE\s+FROM|SELECT\s+.+\s+INTO)\b', 'i') THEN 'DML_SOSPITOS'
            WHEN REGEXP_LIKE(s.text, '\bBULK\s+COLLECT\b|\bFORALL\b', 'i') THEN 'OPTIMITZAT'
        END AS marca
    FROM dba_source s
    JOIN objectes_en_rang o ON s.owner = o.owner AND s.name = o.object_name AND s.type = o.object_type
),
analisis_proximitat AS (
    SELECT owner, name, type, line, text, marca,
        LEAD(marca) OVER (PARTITION BY owner, name, type ORDER BY line) as seguent_marca,
        LEAD(line) OVER (PARTITION BY owner, name, type ORDER BY line) - line as distancia
    FROM linies_clau
    WHERE marca IS NOT NULL
)
SELECT DISTINCT owner AS esquema, name AS objecte, type AS tipus,
    'Possible LOOP amb DML a la línia ' || line AS detall_auditoria
FROM analisis_proximitat
WHERE marca = 'INICI_LOOP' AND seguent_marca = 'DML_SOSPITOS' AND distancia < 25
  AND NOT EXISTS (
      SELECT 1 FROM linies_clau lc 
      WHERE lc.owner = analisis_proximitat.owner AND lc.name = analisis_proximitat.name AND lc.marca = 'OPTIMITZAT'
  )
ORDER BY owner, name;
```

---

```sql
-- =============================================================================
-- CHECK 12: CANDIDATS PER A BULK COLLECT / CÀRREGA MASSIVA
-- Severitat: BAIX
-- Criteri:
--   Identifica codi PL/SQL recent que processa files una a una sense BULK
--   COLLECT/FORALL, per a optimització de rendiment.
-- =============================================================================

WITH esquemes_valids AS (
    SELECT username AS owner FROM dba_users
    WHERE oracle_maintained = 'N'
      AND username NOT IN ('SYS','SYSTEM','DBSNMP','SYSMAN','ORACLE_OCM','OUTLN','WMSYS','XDB','OLAPSYS','MDSYS','CTXSYS','EXFSYS','ORDSYS','ORDPLUGINS','DMSYS','OJVMSYS','AUDSYS','LBACSYS','GSMADMIN_INTERNAL','ANONYMOUS','DIP','APPQOSSYS','ORDDATA','SI_INFORMTN_SCHEMA','SYSKM','SYSBACKUP','SYSDG','SYSRAC','AUSYS','DBSFWUSER','REMOTE_SCHEDULER_AGENT','MDDATA','OWBSYS','OWBSYS_AUDIT','FLOWS_FILES','APEX_PUBLIC_USER','XS$NULL','SPATIAL_CSW_ADMIN_USR','SPATIAL_WFS_ADMIN_USR','MGMT_VIEW','PDBADMIN','DVSYS','DVF','GGSYS','SYSAUX')
      AND username NOT LIKE 'APEX_%' AND username NOT LIKE 'FLOWS_%' AND username NOT LIKE 'ORDS%' AND username NOT LIKE 'ORACLE_%'
),
objectes_modificats AS (
    SELECT owner, object_name, object_type, last_ddl_time FROM dba_objects
    WHERE last_ddl_time BETWEEN TO_DATE(&start_at, 'YYYY-MM-DD HH24:MI:SS') AND TO_DATE(&end_at, 'YYYY-MM-DD HH24:MI:SS')
      AND object_type IN ('PROCEDURE', 'FUNCTION', 'PACKAGE BODY')
      AND owner IN (SELECT owner FROM esquemes_valids)
),
analisi_codi AS (
    SELECT s.owner, s.name, s.type,
        MAX(CASE WHEN REGEXP_LIKE(s.text, '\bBULK\s+COLLECT\b|\bFORALL\b', 'i') THEN 1 ELSE 0 END) as te_bulk,
        MAX(CASE WHEN REGEXP_LIKE(s.text, '\bFETCH\s+\w+\s+INTO\b', 'i') THEN 1 ELSE 0 END) as te_fetch_single,
        MAX(CASE WHEN REGEXP_LIKE(s.text, '\b(INSERT\s+INTO|UPDATE\s+\S+\s+SET|DELETE\s+FROM)\b', 'i') THEN 1 ELSE 0 END) as te_dml,
        MAX(CASE WHEN REGEXP_LIKE(s.text, '\bLOOP\b|\bFOR\s+\w+\s+IN\b', 'i') THEN 1 ELSE 0 END) as te_loop
    FROM dba_source s
    JOIN objectes_modificats o ON s.owner = o.owner AND s.name = o.object_name AND s.type = o.object_type
    GROUP BY s.owner, s.name, s.type
)
SELECT a.owner AS esquema, a.name AS objecte, a.type AS tipus, TO_CHAR(o.last_ddl_time, 'YYYY-MM-DD HH24:MI') AS data_modificacio, a.te_bulk AS te_bulk,
    CASE
        WHEN a.te_fetch_single = 1 AND (a.te_dml = 1 AND a.te_loop = 1) THEN 'FETCH fila a fila + DML en loop: candidat prioritari a BULK COLLECT+FORALL'
        WHEN a.te_fetch_single = 1 THEN 'FETCH fila a fila sense BULK COLLECT: revisar per optimitzar'
        ELSE 'DML en loop sense FORALL: considerar FORALL per a càrrega massiva'
    END AS recomanacio
FROM analisi_codi a
JOIN objectes_modificats o ON a.owner = o.owner AND a.name = o.object_name AND a.type = o.object_type
WHERE a.te_bulk = 0 AND (a.te_fetch_single = 1 OR (a.te_dml = 1 AND a.te_loop = 1))
ORDER BY a.owner, a.type, a.name;
```
