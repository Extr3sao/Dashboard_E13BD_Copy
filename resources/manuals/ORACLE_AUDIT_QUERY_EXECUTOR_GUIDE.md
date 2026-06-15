# Oracle Audit Query Executor Guide

Document unificat de `DOCUMENTACIO_AUDITORIA.md` i `README_AUDIT.md` per operar un agent especialitzat en execucio de consultes d'auditoria Oracle.

## Objectiu
Automatitzar l'analisi d'obsolescencia d'esquemes Oracle amb criteri DBA, traçabilitat completa i decisio segura.

## Prerequisits operatius
- Perfil de connexio valid a `config/Cadena_conexions.txt`
- `DEFAULT_PROFILE` configurat al `.env`
- Oracle client configurat (si aplica)

## Dimensions d'analisi
- Mida real en GB
- Activitat DDL/DML i recencia
- Dependències entrants i sortints
- Jobs, triggers i APEX
- Referencies de codi i objectes invalids

## Pla de consultes base (Q01..Q19)
- Q01_SUMMARY_360: resum integral de risc i activitat
- Q02_SIZE: mida de segments
- Q03_USER_ACCOUNT: estat de compte i dates
- Q04_ACTIVITY_CLASS: classificacio d'activitat
- Q05_OBJECTS_BY_TYPE: inventari per tipus
- Q06_RECENT_DDL: canvis DDL recents
- Q07_TABLE_STATS: recencia d'estadistiques
- Q08_DEPS_INCOMING: dependencies entrants
- Q09_DEPS_OUTGOING: dependencies sortints
- Q10_SYNONYMS: sinonims vinculats
- Q11_GRANTS_GIVEN: permisos atorgats
- Q12_GRANTS_RECEIVED: permisos rebuts
- Q13_SYS_PRIVS: privilegis de sistema
- Q14_CODE_REFS_*: referencies de codi
- Q15_JOBS: jobs scheduler
- Q16_TRIGGERS_ENABLED: triggers habilitats
- Q17_APEX_APPS: apps APEX
- Q18_DB_LINKS: db links
- Q19_INVALID_OBJECTS: objectes invalids

## Score d'obsolescencia (v4)
- Activitat DML nul·la + stats nul·les: +25
- Dependències: fins +30 (penalitza si n'hi ha)
- Login inactiu >180 dies: +10
- Mida: <50MB +20, <1GB +10
- Sense automatismes/codi: +15; amb bloquejadors penalitza fins -40
- Nota final = clamp entre 0 i 100

## Criteri de decisio
- NO ELIMINAR: existeixen bloquejadors (deps entrants, jobs, triggers, APEX o codi)
- PRECAUCIO: senyals de recencia o evidencies parcials
- ELIMINAR: sense activitat ni bloquejadors, amb evidencia suficient

## Sortida minima de l'agent
- Resum executiu per esquema
- Score i desglossament de factors
- Llistat complet de consultes executades i estat
- Recomanacio operativa final
