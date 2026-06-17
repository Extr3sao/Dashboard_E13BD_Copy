# Dashboard E13BD

Portal intern per a auditoria Oracle, control post-CRQ i automatitzacions de distribucio d'informes.

## Objectiu

El projecte unifica en una sola aplicacio:

- auditoria d'obsolescencia d'esquemes Oracle
- auditoria post-CRQ basada en checks SQL
- gestio de controls, regles i cues de treball
- programacio de jobs i distribucio automatica per lots
- ajuda operativa integrada al frontend

## Estat verificat

Verificat el 27 de marc de 2026.

Frontend:

- `npm run lint` -> OK
- `npx vitest run --reporter=dot` -> `66 passed`, `26 files passed`
- smoke browser disponibles i validats:
  - `npm run smoke:ui`
  - `npm run smoke:ui:real`
  - `npm run smoke:ui:oracle` (opt-in, requereix Oracle real i variables d'entorn)
  - `npm run smoke:ui:error`
  - `npm run smoke:ui:load-error`
  - `npm run smoke:ui:profiles-error`
  - `npm run smoke:ui:a11y`

Backend:

- `.venv\Scripts\python.exe -m pytest -q` -> `194 passed`
- l'entorn de test backend queda aillat de plugins globals via `pytest.ini` i `sitecustomize.py`
- eliminades les deprecacions propies de `FastAPI on_event` i `datetime.utcnow()`
- runner estable per a la regressio backend per blocs:
  - `.venv\Scripts\python.exe scripts\run_backend_regression.py`
  - blocs actuals:
    - `test_main_runtime`, `test_post_crq_audit`, `test_post_crq_wrapped_sql`, `test_check11_ai`
    - `test_report_generation`
    - `test_automation`, `test_checks_admin_router`, `test_ai_assistant`, `test_ai_integration`
    - `test_query_sync_service`, `test_internal_db`, `test_db_manager`, `test_config_loader`, `test_audit_plan_engine`, `test_post_crq_pipeline`
- runner monolític backend opcional:
  - `.venv\Scripts\python.exe scripts\run_backend_regression_full.py`
  - última passada verificada: `194 passed`
- regressió completa del projecte:
  - `.venv\Scripts\python.exe scripts\run_project_regression.py` -> OK en mode `stable`
  - `BACKEND_REGRESSION_MODE=full` -> OK en mode `full`

Advertencies conegudes, no bloquejants:

- encara hi ha marge per fer alguns fluxos totalment timezone-aware de cap a cap, pero la suite ja no mostra deprecacions propies per `utcnow()` ni per `on_event`.

## Stack

- Frontend: React 19 + Vite + Vitest + Playwright
- Backend: FastAPI
- BBDD externa: Oracle
- Persistencia interna: SQLite
- Fitxers: `data/`, `logs/`
- IA opcional: OpenRouter

## Arquitectura

Flux principal:

1. L'usuari obre la SPA React de `src/web-app`.
2. El frontend crida endpoints de FastAPI exposats des de `src/api/main.py`.
3. FastAPI resol la peticio contra Oracle, SQLite intern, sistema de fitxers i, quan toca, serveis IA opcionals.
4. El backend retorna JSON, ZIP, TXT, CSV o PDF segons el flux.

Moduls principals:

- `src/web-app/`: SPA React/Vite
- `src/api/main.py`: punt d'entrada HTTP i muntatge de la SPA
- `src/api/audit_engine.py`: auditoria d'obsolescencia
- `src/api/post_crq_audit.py`: execucio i modelat de l'auditoria post-CRQ
- `src/api/automation_service.py`: scheduler, execucio de jobs i distribucio
- `src/api/checks_admin_router.py`: gestio del cataleg de checks SQL
- `src/api/master_lot_backfill.py`: backfill del cataleg mestre de lots
- `src/core/internal_db.py`: persistencia SQLite del cataleg intern
- `src/core/automation_store.py`: persistencia SQLite de l'operativa d'automatitzacions
- `src/core/config_loader.py`: perfils, `.env` i configuracio general

## Frontend actual

El contenidor principal es [App.jsx](src/web-app/src/App.jsx), ja reduit a shell i orquestracio.

Peces de shell:

- `src/web-app/src/components/AppShellChrome.jsx`
- `src/web-app/src/components/AppPageHeader.jsx`
- `src/web-app/src/content/pageHelp.js`
- `src/web-app/src/components/PageHelpButton.jsx`

Workspace principal de la funcionalitat activa:

- `src/web-app/src/views/DatabaseAuditWorkspace.jsx`

Subpagines actives dins `Auditoria BBDD`:

- `Analisi obsolets`
- `Repositori d'obsolets`
- `Auditoria de canvis`
- `Automatitzacions`
- `Tasques i regles`
- `Gestio de controls`
- `Configuracio del servidor`
- `Guia i Ajuda`

Hooks globals del shell:

- `src/web-app/src/hooks/usePersistedNavigationState.js`
- `src/web-app/src/hooks/useProfiles.js`
- `src/web-app/src/hooks/useGlobalReport.js`

Hooks de domini principals:

- `src/web-app/src/hooks/useDeepScan.js`
- `src/web-app/src/hooks/usePostCrqAudit.js`

Automatitzacions queda separada en vista, hooks i panels:

- `src/web-app/src/views/AutomationView.jsx`
- `src/web-app/src/hooks/useAutomationViewModel.js`
- `src/web-app/src/hooks/useAutomationJobs.js`
- `src/web-app/src/hooks/useAutomationLots.js`
- `src/web-app/src/hooks/useAutomationHistoryRetries.js`
- `src/web-app/src/hooks/useAutomationRoutesTemplates.js`
- `src/web-app/src/hooks/useAutomationAnalytics.js`
- `src/web-app/src/components/automation/`

## Persistencia i dades

Hi ha dos SQLite interns separats:

- `internal.db`
  - checks SQL
  - registre d'obsolets
  - metadades internes
- `automation.db`
  - jobs programats
  - execucions
  - historial i cues de reintent
  - rutes i plantilles de distribucio

La resolucio del path SQLite es fa a `src/core/sqlite_paths.py`.

Perfils Oracle:

- fitxer: `config/Cadena_conexions.txt`

Format:

```txt
## NOM_PERFIL
USER = usuari
PASSWORD = password
DSN = host:port/service
```

Configuracio general:

- `config/config.yaml`
- `config/.env`

Variables utiles:

- `DEFAULT_PROFILE`
- `CONNECTIONS_FILE`
- `ORACLE_CLIENT_LIB_DIR`
- `INTERNAL_DB_PATH`
- `AUTOMATION_DB_PATH`

## Fluxos principals

### 1. Analisi d'obsolescencia

1. L'usuari introdueix esquemes al frontend.
2. `useDeepScan` crida el backend d'auditoria.
3. El motor consulta Oracle i calcula score, risc i evidencies.
4. El resultat es mostra en pantalla i es pot exportar a informe.

### 2. Auditoria post-CRQ

1. L'usuari selecciona perfil, checks, rang temporal i esquemes.
2. `usePostCrqAudit` executa els checks SQL definits al cataleg intern.
3. Els resultats es classifiquen per criticitat, lot i resum executiu.
4. Es poden generar ZIP, TXT i PDF per distribucio o analisi.

### 3. Automatitzacions

1. Es configuren jobs, lots, destinataris i plantilles.
2. `automation_service.py` planifica i executa les feines.
3. L'estat operatiu queda a `automation.db`.
4. Els informes es distribueixen segons lots, rutes i plantilles.
5. Si hi ha errors, els reenviaments passen a la cua de reintents.

## Arrencada

### Requisits previs

- Windows PowerShell
- Python disponible al `PATH`
- Node.js i npm disponibles al `PATH`
- fitxer `.env` configurat a partir de `.env.example`, si cal
- perfils Oracle configurats a `config/Cadena_conexions.txt`, si cal connexio real a Oracle

### Opcio unificada

Des de l'arrel del projecte, executa:

```powershell
.\run.ps1
```

Important: en PowerShell cal usar `.\run.ps1`. No facis servir `\run.ps1`, perque la barra inicial busca l'script a l'arrel del disc (`C:\run.ps1`) i no a la carpeta actual.

Si PowerShell bloqueja l'execucio de scripts, pots permetre-la nomes per a la sessio actual:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\run.ps1
```

L'script `run.ps1`:

1. crea `.venv` si no existeix, o el recrea si apunta a una instal.lacio de Python que ja no existeix
2. installa dependencies Python
3. crea les bases SQLite locals si no existeixen
4. carrega dades inicials segures si les bases estan buides
5. entra a `src/web-app`
6. installa dependencies Node si cal
7. executa `npm run build`
8. arrenca `uvicorn src.api.main:app --host 127.0.0.1 --port 8000`

Quan el servidor estigui arrencat, obre:

```text
http://127.0.0.1:8000
```

### Dades inicials

En una descarrega neta, el primer `.\run.ps1` carrega automaticament les dades de:

```text
resources/bootstrap/initial_data.json
```

Aixo deixa visibles dades de partida per a:

- jobs programats
- lots mestres
- mapatge `schema -> lot`
- destinataris per lot
- plantilles de distribucio

Aquest fitxer no conte contrasenyes, cadenes Oracle reals, `.env` ni bases SQLite. Les bases locals es creen fora del repo, per defecte a:

```text
%LOCALAPPDATA%\OracleAudit\internal.db
%LOCALAPPDATA%\OracleAudit\automation.db
```

Si ja hi ha dades locals, el bootstrap es salta i no les sobreescriu.

Per arrencar sense carregar dades inicials:

```powershell
$env:BOOTSTRAP_INITIAL_DATA='0'
.\run.ps1
```

Per usar un bootstrap privat propi:

```powershell
$env:BOOTSTRAP_DATA_PATH='resources\bootstrap\initial_data.local.json'
.\run.ps1
```

Els fitxers `resources/bootstrap/*.local.json` estan ignorats per Git per evitar publicar dades internes.

#### SMTP i mapa de proveidors en una instal.lacio nova

La configuracio real del servidor SMTP, contrasenyes i correus interns no es publica al repositori. Perque una instal.lacio nova ja arrenqui amb aquestes dades, crea el fitxer privat:

```text
resources/bootstrap/initial_data.local.json
```

Abans del primer `.\run.ps1`, omple'l amb una estructura com aquesta:

```json
{
  "delivery_config": {
    "smtp_host": "smtp.el_teu_servidor.cat",
    "smtp_port": 587,
    "smtp_username": "usuari",
    "smtp_password": "contrasenya-privada",
    "smtp_use_tls": true,
    "from_email": "oracle-audit@gencat.cat",
    "default_recipients": [
      "destinatari@gencat.cat"
    ],
    "failure_notification_recipients": [
      "avisos@gencat.cat"
    ]
  },
  "delivery_routes": {
    "tic_summary_recipients": [
      "tic@gencat.cat"
    ],
    "providers": [
      {
        "provider_code": "AM05",
        "label": "AM05",
        "emails": [
          "proveidor-am05@gencat.cat"
        ],
        "enabled": true
      },
      {
        "provider_code": "AM07",
        "label": "AM07",
        "emails": [
          "proveidor-am07@gencat.cat"
        ],
        "enabled": true
      }
    ]
  }
}
```

Despres executa:

```powershell
.\run.ps1
```

El primer arrencat carrega `resources/bootstrap/initial_data.json` i, si existeix, aplica despres `resources/bootstrap/initial_data.local.json` amb `force=True`. Si el PC ja havia arrencat abans i les bases locals ja existeixen, pots aplicar la capa privada igualment amb:

```powershell
python scripts\bootstrap_initial_data.py --data resources\bootstrap\initial_data.local.json --force
```

Mantingues aquest fitxer fora de Git: pot contenir password SMTP, correus interns i altres dades privades.

### Configuracio BBDD Oracle

El repositori no publica credencials ni cadenes de connexio reals. Per aixo `config/Cadena_conexions.txt` esta ignorat per Git.

En el primer `.\run.ps1`, si no existeix, es crea automaticament a partir de:

```text
config/Cadena_conexions.example.txt
```

Abans d'executar consultes contra Oracle real, edita:

```text
config/Cadena_conexions.txt
```

Format:

```txt
## E13BD
USER = usuari_oracle
PASSWORD = contrasenya_oracle
DSN = host:1521/servei
```

Si vols definir quin perfil s'usa per defecte, crea o edita `config/.env`:

```env
DEFAULT_PROFILE=E13BD
CONNECTIONS_FILE=config\Cadena_conexions.txt
ORACLE_CLIENT_LIB_DIR=C:\oracle\instantclient
```

Notes:

- `ORACLE_CLIENT_LIB_DIR` nomes cal si la instal.lacio Oracle ho requereix.
- Sense configurar `config/Cadena_conexions.txt`, l'aplicacio pot arrencar i mostrar les dades inicials locals, pero les consultes contra Oracle real fallaran o no retornaran dades reals.
- No s'ha de pujar mai `config/Cadena_conexions.txt`, `config/.env`, `.env` ni cap fitxer `.db` amb dades reals al repositori.

### Opcio manual

Backend:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Frontend en desenvolupament:

```powershell
cd src\web-app
npm install
npm run dev
```

## Testing

Runbook operatiu curt:

- [operational-runbook.md](C:\Users\45485456N\OneDrive%20-%20Generalitat%20de%20Catalunya\.....Antigravity\Dashboard%20E13BD\operational-runbook.md)

Frontend, des de `src/web-app`:

```powershell
npm run lint
npx vitest run --reporter=dot
npm run smoke:ui
npm run smoke:ui:real
npm run smoke:ui:oracle
npm run smoke:ui:error
npm run smoke:ui:load-error
npm run smoke:ui:profiles-error
npm run smoke:ui:a11y
```

Backend, des de l'arrel del repo:

```powershell
.venv\Scripts\python.exe scripts\run_backend_regression.py
```

Aquest runner executa els blocs `pytest` estables en seqüència per evitar els timeouts de la invocació monolítica sobre tota la suite.
També fixa `--basetemp` dins `output/pytest-regression` per evitar soroll de neteja de temporals a `%TEMP%` en Windows.

Runner monolític opcional del backend:

```powershell
.venv\Scripts\python.exe scripts\run_backend_regression_full.py
```

Per defecte usa un timeout de `1800s` i també fixa `--basetemp` dins `output/pytest-regression/full-suite`.
Si cal, es pot ajustar amb:

```powershell
$env:BACKEND_REGRESSION_TIMEOUT_SECONDS='2400'
.venv\Scripts\python.exe scripts\run_backend_regression_full.py
```

Regressió estable del projecte complet, des de l'arrel del repo:

```powershell
.venv\Scripts\python.exe scripts\run_project_regression.py
```

Aquest runner encadena:

- regressió backend per blocs per defecte
- `npm run lint`
- `npx vitest run --reporter=dot`
- `npm run build`
- `npm run smoke:ui`
- `npm run smoke:ui:real`
- `npm run smoke:ui:oracle` si detecta:
  - `ORACLE_SMOKE_CONNECTIONS_FILE`
  - `ORACLE_SMOKE_PROFILE`
  - `ORACLE_SMOKE_SCHEMA`

Si aquestes variables no hi són, el runner el deixa com a `skip` explícit i continua amb la regressió estable normal.

Per forçar el runner backend monolític dins aquesta regressió completa:

```powershell
$env:BACKEND_REGRESSION_MODE='full'
.venv\Scripts\python.exe scripts\run_project_regression.py
```

Valors admesos:

- `stable` -> runner backend per blocs
- `full` -> runner backend monolític

El harness `smoke:ui:real` reintenta automàticament el seed inicial, l'arrencada de FastAPI i l'arrencada de Vite fins a 3 cops si detecta una fallada transitòria abans que el servei estigui llest.
El harness `smoke:ui` usa `vite preview` sobre `dist` i reintenta automàticament l'arrencada fins a 3 cops si detecta una fallada transitòria abans que el servidor mockejat estigui llest.
El harness `smoke:ui:real` usa FastAPI real servint el frontend construït des de `dist`, de manera que el camí estable no depèn d'HMR de `vite dev`.
Els tres harnesses Playwright comparteixen runtime a `src/web-app/scripts/smokeRuntime.mjs` per unificar `launch`, `spawn`, `close` i `retry`.

Smoke Oracle opt-in, des de `src/web-app`:

```powershell
$env:ORACLE_SMOKE_CONNECTIONS_FILE='C:\\ruta\\Cadena_conexions.txt'
$env:ORACLE_SMOKE_PROFILE='E13BD'
$env:ORACLE_SMOKE_SCHEMA='APP_USER'
$env:ORACLE_SMOKE_POST_CRQ_SCHEMAS='APP_USER,CORE_DB'   # opcional
$env:ORACLE_SMOKE_INTERNAL_DB_SOURCE='data\\e13bd.db'   # opcional, per reutilitzar el cataleg real de lots
$env:ORACLE_SMOKE_REQUIRE_PROVIDER='1'                  # opcional, falla si no hi ha proveidors/lots reals
npm run smoke:ui:oracle
```

Exemple real validat amb proveidor:

```powershell
$env:ORACLE_SMOKE_CONNECTIONS_FILE='config\\Cadena_conexions.txt'
$env:ORACLE_SMOKE_PROFILE='E13BD'
$env:ORACLE_SMOKE_SCHEMA='ABOIX'
$env:ORACLE_SMOKE_POST_CRQ_SCHEMAS='E13_RALC'
$env:ORACLE_SMOKE_INTERNAL_DB_SOURCE='data\\e13bd.db'
$env:ORACLE_SMOKE_REQUIRE_PROVIDER='1'
npm run smoke:ui:oracle
```

El harness Oracle:

- arrenca FastAPI real en un port separat
- usa `internal.db` copiada a un entorn temporal, o la base indicada a `ORACLE_SMOKE_INTERNAL_DB_SOURCE`
- crea `automation.db` temporal
- valida abans la connexio amb `POST /api/db/test`
- executa `deep scan` i `post-CRQ` reals des de navegador
- valida el `run` Post-CRQ i dues descàrregues reals: `ZIP` i `Resum general`
- intenta també `provider` si el resultat real conté lots/proveïdors; si no n'hi ha, el smoke el deixa com a `skip` traçat
- si `ORACLE_SMOKE_REQUIRE_PROVIDER='1'`, el smoke falla si no detecta un proveïdor/lot real
- reintenta automàticament l'arrencada de FastAPI i Vite fins a 3 cops si hi ha una fallada transitòria d'inici
- reutilitza el `report_data` del `run` quan el frontend el té disponible, evitant reexecutar l'auditoria per generar `ZIP` i `Resum general`

Backend, des de l'arrel del repo:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Cobertura funcional actual del frontend:

- shell principal i ajuda contextual
- deep scan
- post-CRQ
- automatitzacions: jobs, lots, historial, reintents, destinataris, plantilles i dashboard
- mail config, checks admin, regles, repositori d'obsolets, guia i help views
- escenaris browser smoke mockejats de cami felic, errors operatius, errors de carrega, error de perfils i accessibilitat basica
- smoke amb backend FastAPI real, SQLite temporal i dades semilla sense interceptar `/api`

## Estructura rellevant

```txt
config/                  configuracio, perfils i .env
data/                    snapshots i informes generats
logs/                    logs d'execucio
scripts/                 scripts auxiliars
src/api/                 API FastAPI i serveis operatius
src/core/                configuracio, acces Oracle i SQLite intern
src/web-app/             frontend React/Vite
tests/                   tests Python
run.ps1                  build frontend + arrencada del sistema unificat
run-clean.ps1            variant d'arrencada/neteja
```

## Notes operatives

- El backend concentra la major part de la logica de negoci.
- El frontend actua com a shell d'operacio, configuracio, seguiment i distribucio.
- L'ajuda integrada i els botons `(i)` expliquen l'objectiu de cada pantalla sense sortir del producte.
- Si es vol continuar endurint el sistema, el retorn mes alt ja no esta en mes unit tests frontend, sino en ampliar els E2E amb backend real cap a fluxos Oracle controlats.
