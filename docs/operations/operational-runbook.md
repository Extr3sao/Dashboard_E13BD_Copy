# Runbook Operatiu

## Objectiu
Guia curta de com arrencar, validar i tancar regressions segons l'escenari mes habitual.

## Escenaris recomanats

### 1. Validacio diaria rapida
Des de l'arrel del repo:

```powershell
.venv\Scripts\python.exe scripts\run_backend_regression.py
cd src\web-app
npm run lint
npx vitest run --reporter=dot
```

Quan usar-ho:
- canvis petits de backend o frontend
- abans de fer commit local

### 2. Validacio frontend estable
Des de `src/web-app`:

```powershell
npm run build
npm run smoke:ui
npm run smoke:ui:real
```

Quan usar-ho:
- canvis UI
- wiring amb FastAPI real sense Oracle
- regressions visibles de navegacio

### 3. Validacio backend estable
Des de l'arrel del repo:

```powershell
.venv\Scripts\python.exe scripts\run_backend_regression.py
```

Quan usar-ho:
- backend diari
- quan la suite completa seria massa lenta per la iteracio actual

### 4. Validacio backend forta
Des de l'arrel del repo:

```powershell
.venv\Scripts\python.exe scripts\run_backend_regression_full.py
```

Opcional amb timeout superior:

```powershell
$env:BACKEND_REGRESSION_TIMEOUT_SECONDS='2400'
.venv\Scripts\python.exe scripts\run_backend_regression_full.py
```

Quan usar-ho:
- abans de tancar una fase gran
- abans d'un lliurament intern
- quan vols confirmar que la suite completa passa en una sola invocacio

### 5. Regressio completa del projecte
Des de l'arrel del repo:

```powershell
.venv\Scripts\python.exe scripts\run_project_regression.py
```

Per forcar backend monolitic:

```powershell
$env:BACKEND_REGRESSION_MODE='full'
.venv\Scripts\python.exe scripts\run_project_regression.py
```

Quan usar-ho:
- abans de donar per bona una tanda gran de canvis
- quan toques backend + frontend + smoke

### 6. Smoke Oracle real
Des de `src/web-app`:

```powershell
$env:ORACLE_SMOKE_CONNECTIONS_FILE='config\\Cadena_conexions.txt'
$env:ORACLE_SMOKE_PROFILE='E13DB'
$env:ORACLE_SMOKE_SCHEMA='ABOIX'
$env:ORACLE_SMOKE_POST_CRQ_SCHEMAS='E13_RALC'
$env:ORACLE_SMOKE_INTERNAL_DB_SOURCE='data\\e13bd.db'
$env:ORACLE_SMOKE_REQUIRE_PROVIDER='1'
npm run smoke:ui:oracle
```

Quan usar-ho:
- validar `deep scan` i `post-CRQ` contra Oracle real
- verificar `provider` real en Post-CRQ

## Senyals normals que no son fallo de producte
- `frontend smoke oracle skipped`
  - normal si falten variables Oracle al runner de projecte
- logs backend al fitxer `src/web-app/output/playwright/.../*.log`
  - normal; els smoke real/Oracle ja no els aboquen a consola
- `stable` i `full` no s'han d'executar en paral·lel sobre el mateix workspace
  - poden fer flaky Vitest per contencio

## Ordre recomanat per tancament fort
1. `scripts/run_backend_regression.py`
2. `cd src/web-app && npx vitest run --reporter=dot`
3. `cd src/web-app && npm run smoke:ui:real`
4. `scripts/run_project_regression.py`
5. `scripts/run_backend_regression_full.py` si vols tancament backend fort

## Fitxers clau
- `scripts/run_backend_regression.py`
- `scripts/run_backend_regression_full.py`
- `scripts/run_project_regression.py`
- `src/web-app/scripts/playwright-smoke.mjs`
- `src/web-app/scripts/playwright-smoke-real.mjs`
- `src/web-app/scripts/playwright-smoke-oracle.mjs`
