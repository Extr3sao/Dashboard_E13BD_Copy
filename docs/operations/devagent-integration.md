# Integració de DEV Agent a Dashboard E13BD

Estat: **integrat i verificat (AUDITED) — certificació del producte NO assolida**
Data: 2026-09-18
Autoritat d'evidència: `GLOBAL_RUN_ID_REGISTRY_WRITE_ONCE` (`.devagent/state/registry.json`)

## 1. Framework

| Camp | Valor |
| --- | --- |
| Source autoritzat | `C:\Users\GVLLFR0035\OneDrive - Generalitat de Catalunya\Vault Job\30 - RECURSOS\30.09.- DEV Agentic Portable` |
| Instal·lació | `pipx` (venv `C:\Users\GVLLFR0035\AppData\Local\pipx\pipx\venvs\devagent`), entrypoint `C:\Users\GVLLFR0035\.local\bin\devagent` |
| Versió real | `DEV Agent 4.5.1` (identity 4.5.1, `matches_distribution: true`) |
| Release | `REL-4.5.1-E6116BDBD69B` (`package_sha256 e6116bdbd69bb2b1d1c22a561b0cd59c9f3a0596df76f07f38dc2620840d4933`) |
| Baseline inclosa | `4.3.0 CERTIFIED (CERT-4.3.0-ARCHIFY-CF79888BF56D) + … + DEF-451 BROWNFIELD FOUNDATIONAL CONTEXT (4.5.1) — PREPARED AND TESTED, NOT RELEASED` |
| CLI | `version, validate, capabilities, release-verify, doctor, init, run, audit, verify, upgrade, project-doctor` |

No s'ha instal·lat el paquet homònim de PyPI `devagent 1.1.0` (és un producte diferent).

El source 4.5.1 **sí** conté la implementació brownfield requerida: `core/lifecycle/intent.py`
(contractes per intent, `AUDIT_ONLY → AUDITED`), `devagent_project/audit.py`
(foundational context / AS-IS / entrypoints / risk register / gap analysis), boundary
`PROJECT_BOUNDARY_V1` i terminalització garantida de runs.

## 2. Inicialització del projecte

```text
project_id            dashboard-e13bd-2695770f
project_name          Dashboard E13BD
required_devagent     >=4.5 (compatible=true, COMPATIBLE)
execution_mode        GOVERNED_AUTONOMOUS
created_by            devagent 4.5.1 init
declaration_files     requirements.txt, src/web-app/package.json
fingerprint           bc80cf9cc411cae2
framework_copied      false   (només .devagent/{project.yaml,state,evidence,runs,cache})
```

El `.devagent` manual anterior (no generat pel framework) es va **arxivar, no destruir**, a
`.devagent.pre-framework-audit/` (20 fitxers: 3 ADRs, audit manual, pla de rollback,
evidència crua i els dos intents d'init previs amb el seu propi registry/run
`RUN-9B579779FFC44F6E`). Inventari SHA-256 complet a
`docs/operations/devagent-evidence/MANUAL_DEVAGENT_ARCHIVE.sha256`
(`BUNDLE_SHA256 ac0b7be3a0e9e2f2c634bfd980fbd9cb52c5970f7a222a3762cbaceb7e192d86`, 20 fitxers).

## 3. Boundary i stack (descobriment real)

- Topologia: `root-plus-workspace` (workspace `web-app` → `src/web-app`).
- Categoria d'exclusions: `CACHE`, `DEPENDENCY`, `GENERATED`, `TOOL_STATE`, amb regles
  `marker:cache directory signature`, `node_modules/.package-lock.json`, `pyvenv.cfg`,
  `segment:.da`, `segment:.devagent`, `segment:.git`, `segment:__pycache__`,
  `segment:dist`, `segment:env`.
- `declaration_pollution = 0`, `manifest_declaration_contamination = 0`,
  `manifest_identity_status = CLEAN` → **cap contaminació de `.venv` ni `node_modules`**
  a les declaracions pròpies.
- Stack detectat: `python` + `node` + `frontend-framework`; build `npm run build`;
  dependency managers `pip`, `npm`; test frameworks `pytest`, `vitest`.
- Entrypoints: després de declarar `"main": "src/main.jsx"` a `src/web-app/package.json`,
  `ENTRYPOINTS.json` passa de `count: 0` (unknown) a `count: 2` (`src/main.jsx`,
  evidència `src/web-app` i `src/web-app/package.json`). L'entrypoint del backend
  (`src/api/main.py`, `run.ps1`) no és estable pel descobridor perquè el repositori no
  té cap declaració d'entrypoint Python (gap documentat, vegeu §7).

## 4. Runs del framework (terminalització)

| run_id | origen | intent | RESERVED | TERMINAL | terminal_state | receipt_sha256 |
| --- | --- | --- | --- | --- | --- | --- |
| `RUN-E2683309284B4E77` | `devagent init . --audit` | AUDIT_ONLY | 1 | 1 | `AUDITED` (SUCCESS) | `a367536c…` |
| `RUN-D9B10996B14A4CD5` | `devagent audit .` | AUDIT_ONLY | 1 | 1 | `AUDITED` (SUCCESS) | `69a3f443…` |
| `RUN-52D74655315E4692` | `devagent run … --intent DISCOVERY_ONLY` | DISCOVERY_ONLY | 1 | 1 | `DISCOVERED` (SUCCESS) | — |
| `RUN-D33BDFDB5DEE4EA8` | `devagent audit .` (post-remediació) | AUDIT_ONLY | 1 | 1 | `AUDITED` (SUCCESS) | `—` |
| `RUN-E818C72C45054564` | `devagent audit .` (final, amb docs i bundle d'evidència) | AUDIT_ONLY | 1 | 1 | `AUDITED` (SUCCESS) | `—` |

`orphan_reservations.count = 0`, cap run amb doble terminal. Prova negativa:
`devagent run "…" ./does-not-exist-e13bd --intent DISCOVERY_ONLY` → exit 1
(`MANIFEST_MISSING`) **sense crear reserva** (el run id només es reserva després del
bootstrap del manifest).

Audit-only no reclama mai estats d'implementació: cada receipt declara
`claimed: [DISCOVERED, AUDITED]` i `not_claimed: [IMPLEMENTING, IMPLEMENTED, TESTED,
E2E_VERIFIED, INDEPENDENTLY_VERIFIED, CERTIFIED]`, amb
`product_fingerprint_before == product_fingerprint_after` i `product_files_modified: 0`.

## 5. Verificació i salut

```text
devagent verify .          → VERIFY=PASS
devagent project-doctor .  → all_ok: true
   boundary_status OK · declaration_pollution 0 · orphan_reservations 0 (action_required false)
   evidence_completeness 12/12 (complete true) · compatibility COMPATIBLE
   manifest_identity_status CLEAN · deep_audit_available true
   last_audit RUN-E818C72C45054564 (AUDITED, 29 findings, coverage 1.0)
   last_terminal_state RUN-E818C72C45054564 (SUCCESS, terminal true)
```

`AUDIT_RECEIPT.json` és autocontingut: `receipt_digest` = SHA-256 del receipt
canonicalitzat sense el propi camp digest (verificat: `59b6fd6b…` per `RUN-D9B10996B14A4CD5`),
i el registry enllaça `receipt_sha256` per run.

## 6. Proves executades (2026-09-18)

| Àmbit | Comanda | Resultat |
| --- | --- | --- |
| Backend (blocs) | `python scripts/run_backend_regression.py` | **210 passed**, exit 0 (82/30/70/28) |
| Backend residu | comptatge `src/db/*.db*` abans/després | 4 → 4 (estable, cleanup PASS) |
| Frontend | `vitest run --no-file-parallelism` fitxer a fitxer | **26/26 fitxers, 79/79 tests** |
| Build producció | `vite build` → `src/web-app/dist` | exit 0 (`✓ built in 38–51s`) |
| E2E UI | `node scripts/playwright-smoke.mjs` | exit 0, `[smoke] smoke success` |

Detalls de l'execució frontend: el checkout viu en un volum OneDrive; un run
monoprocess de la suite excedeix qualsevol finestra raonable (un sol fitxer pesant va
consumir 159 s només en `import`). Mitigacions aplicades i documentades:
intèrpret del backend des de disc local (venv `3.14.3` equivalent), `--no-file-parallelism`,
`--max-old-space-size=4096` i agregació dels logs per fitxer amb
`docs/operations/devagent-evidence/tally_frontend_runs.py`.

## 7. Defectes preexistents: diagnòstic i reparació

Classificació: `PRODUCT_DEFECT` / `TEST_DEFECT` / `ENVIRONMENT_DEFECT` / `FLAKY` / `TIME_DEPENDENT`.

| # | Símptoma | Classe | Acció |
| --- | --- | --- | --- |
| 1 | `test_compute_next_run_weekly` falla segons la data de paret | TIME_DEPENDENT | es fixa el rellotge (`now`) sense debilitar l'expectativa |
| 2 | `test_deliver_targets_logs_provider_warning` no arriba mai al `except` | TEST_DEFECT | el fixture activa el target `lots` (contracte real: opt-in de `delivery.targets`) |
| 3 | Família post-CRQ: mocks amb `:start_date/:end_date` | TEST_DEFECT (drift de contracte) | mocks accepten la finestra real `:start_at/:end_at` |
| 4 | Família post-CRQ: presets dinàmics vs dates fixes | TIME_DEPENDENT | finestres explícites deterministes als tests |
| 5 | `_criticality_key` no entén el vocabulari del catàleg (`ALT`, `STOPPER`) i `_resolve_check_criticality` acceptava `"N/A"` com a severitat real | **PRODUCT_DEFECT** | `"N/A"` es tracta com a absència (fallback intern recuperat) i es mapeja `ALT`/`STOPPER` |
| 6 | `_run_single_post_crq_check` no registrava cap WARNING en fallar un check | **PRODUCT_DEFECT** (observabilitat) | es restaura el warning `Post-CRQ check execution failed` |
| 7 | Fallback «safe post CRQ PDF builder» només feia `print` a stderr | **PRODUCT_DEFECT** (observabilitat) | passa a `logger.warning` |
| 8 | `resolved_at`/`generated_at` sense sufix `Z` | **PRODUCT_DEFECT** (format) | s'unifica el timestamp aware |
| 9 | Ajudes contextuals i etiquetes de botó desfasades (`programats`, `Auditar`) | TEST_DEFECT (drift producte↔test) | matchers actualitzats al text vigent |
| 10 | `DeepScanView.test.jsx` no passava `selectedProfile` | TEST_DEFECT (gap de fixture) | s'afegeix la prop requerida |
| 11 | `App.smoke.test.jsx` matava el worker amb heap per defecte | ENVIRONMENT_DEFECT | `--max-old-space-size=4096` |
| 12 | `DatabaseAuditWorkspace.test.jsx` penjava al `Suspense` (import lazy > 1 s amb IO estrangulat) | ENVIRONMENT_DEFECT | `asyncUtilTimeout: 5000` centralitzat a `src/web-app/src/test/setupTests.js` |
| 13 | `playwright-smoke.mjs`: selectors `/^Auditar$/i` i «Regles de severitat i safata interna» | TEST_DEFECT (drift de l'arnès E2E) | selectors al text vigent (`Iniciar Auditoria`, `Regles globals`, `Safata interna de tasques`) |

Cap expectativa s'ha canviat per fabricar un PASS: quan el contracte del producte havia
canviat, s'ha actualitzat el test; quan el producte era defectuós, s'ha corregit el producte.

## 8. Canvis manuals previs al framework (reauditats)

| Fitxer | Classe | Motiu |
| --- | --- | --- |
| `tests/test_automation.py` | VALID_FIX (+ reparacions d'aquesta fase) | leak de SQLite de test, rellotge i opt-in de delivery |
| `tests/test_post_crq_lot_status.py` | VALID_FIX | cleanup de DB de test garantit |
| `.gitignore` | VALID_FIX | ignora `*.db-journal/-wal/-shm` i estat mutable de `.devagent` |
| `README.md` | VALID_DOC_FIX | l'enllaç apuntava a una ruta absoluta d'un altre usuari (`C:\Users\45485456N\…`); ara `docs/operations/operational-runbook.md` |
| `docs/operations/operational-runbook.md` | VALID_DOC_FIX | runbook nou; tots els scripts que cita existeixen i `.venv` respon (3.14.3) |
| `src/db/test_automation_1774598574067934.db-journal` (esborrat) | VALID_FIX | artefacte generat que estava versionat; convé consolidar l'esborrat al commit |

## 9. Revalidació dels hallazgos de l'auditoria manual

| Hallazgo manual | Estat revalidat |
| --- | --- |
| ~4.058 DB SQLite residuals de tests | CERT: ja no es reprodueix (`src/db` estable 4 → 4 en la regressió sencera) |
| 2 fallos backend + 4 frontend preexistents | CERT: 210/210 backend, 79/79 frontend |
| README/runbook trencats | CERT: enllaç corregit, runbook vàlid |
| Gap de CI | CERT pel framework: `GAP-002`, `RISK-003` |
| Dependències no reproduïbles | PARCIAL: `package-lock.json` existeix per npm; Python sense lock/pins → `GAP-003`, `RISK-002` |
| Gap de seguretat | CERT: `RISK-005` (cap política/SAST/secret scanning) |
| Gap d'observabilitat | CERT: `UNKNOWN FC-OBSE-020` + regressions de logging trobades i reparades a `post_crq_audit.py` |
| Superfície de secrets dins el boundary | CERT: `RISK-006` (`.env`, `.env.example`, `config/.env`, `config/.env.bak`, còpia en residus de pytest) — **valors no llegits; requereix revisió humana** |

## 10. Riscos i gaps (framework, run `RUN-D33BDFDB5DEE4EA8`)

29 findings (`OBSERVED 14 / INFERRED 8 / UNKNOWN 7`), cobertura de categories 100 %,
6 riscos i 3 gaps:

- `RISK-002` / `GAP-003` dependències sense lock (severitat MEDIUM, likelihood HIGH).
- `RISK-003` / `GAP-002` sense CI/CD (MEDIUM/HIGH).
- `RISK-004` sense declaració de contenidor/topologia de runtime (LOW/MEDIUM).
- `RISK-005` sense artefactes de governança de seguretat (MEDIUM/MEDIUM).
- `RISK-006` fitxers amb vocabulari de secrets dins el boundary (MEDIUM/MEDIUM).
- `RISK-007` / `GAP-006` àrea no establerta del context (unknowns).
- `UNKNOWN`: deployment, infrastructure, data/schema, security, observability,
  license/compliance, runtime constraints (i entrypoint del backend).

## 11. Traçabilitat

Cadena de canvi documentada a `docs/operations/devagent-evidence/traceability.json`
(`REQ → ACC → IMP → TEST → EXEC → EVID → VERIFIER`) amb cobertura dels 13 defectes
tractats. La cadena d'implementació **del framework** (REQ→ACC→ARCH→WP→IMP→TEST→EXEC→EVID)
no existeix encara perquè no s'ha executat cap run `IMPLEMENTATION`/`VERIFY_ONLY`: el
ledger del framework només reclama `DISCOVERED`/`AUDITED`.

## 12. Portes de l'estat final

```text
DEV_AGENT_INSTALLED      true          PROJECT_DOCTOR            PASS (all_ok true)
FRAMEWORK_SOURCE         AUTHORIZED_LOCAL_SOURCE (4.5.1)   RUN_TERMINALIZATION  PASS (5/5)
PROJECT_INITIALIZED      true          ORPHAN_RUNS               0
FRAMEWORK_COPIED         false         EVIDENCE_AUTHORITY        PASS (registry + receipts + MANIFEST)
PROJECT_BOUNDARY         PASS          TRACEABILITY              100 % canvis de projecte
VENV_POLLUTION           0             INDEPENDENT_VERIFIER      PASS (verify + project-doctor)
NODE_MODULES_POLLUTION   0             FALSE_SUCCESS             0
BACKEND_DISCOVERY        PASS          GOVERNANCE_VIOLATIONS     0
FRONTEND_DISCOVERY       PASS          AUDIT_TERMINAL_STATE      AUDITED
FOUNDATIONAL_CONTEXT     PASS          CERTIFICATION_STATUS      NOT_CERTIFIED
DEEP_AUDIT               PASS
```

## 13. Bloquejadors i recomanacions

Bloquejadors per a la certificació del producte:

1. Cap run del framework ha arribat a `TESTED`/`E2E_VERIFIED`/`INDEPENDENTLY_VERIFIED`:
   la porta A6 exigeix proves executades per la governança, i l'execució de la suite
   dins del run no és viable mentre el checkout visqui en un volum OneDrive estrangulat.
2. Riscos i gaps oberts: CI/CD, pinning de dependències Python, governança de seguretat.
3. Revisió humana de la superfície de secrets (`RISK-006`).
4. Arbre de treball amb canvis sense commitir (reparacions de tests, `.gitignore`,
   `README`, runbook, esborrat del journal) i `.devagent` encara no versionat.

P0: revisió humana de `RISK-006` (confirmar/rotar/eliminar `config/.env.bak` i còpies).
P1: pipeline CI mínim; lock/pins per a Python; run `VERIFY_ONLY` en un checkout local
(NTFS) per obtenir `TESTED`/`E2E_VERIFIED`/`INDEPENDENTLY_VERIFIED`; commit dels canvis.
P2: declarar entrypoint Python (p. ex. `pyproject.toml` amb console script i un `main()`
real a `src/api/main.py`); eliminar `_probe.db` i `internal_fallback.db` (0 bytes);
declarar topologia de runtime/observabilitat; normalitzar el `last_audit` del manifest.

## 14. Evidència

- Framework: `.devagent/state/registry.json`, `.devagent/evidence/<run_id>/*`
  (12 artefactes per run), `AUDIT_RECEIPT.json` amb `receipt_digest`.
- Projecte: `docs/operations/devagent-evidence/*.log` +
  `MANIFEST.sha256` (inventari SHA-256 i digest del bundle:
  `BUNDLE_SHA256 446d4002997804d3ff7417f7f92af95a8ce034e8eff3cbb60a7025a32438a405`, 40 fitxers)
  i `MANUAL_DEVAGENT_ARCHIVE.sha256` per a l'arxiu manual.
- Arxiu del `.devagent` manual: `.devagent.pre-framework-audit/` (preservat).

## 15. Tancament governat de verificació i certificació (2026-09-18, candidat v2)

Aquesta secció substitueix la recomanació P1 de §13 ("run `VERIFY_ONLY` en un
checkout local per obtenir `TESTED`/`E2E_VERIFIED`/`INDEPENDENTLY_VERIFIED`"):
es va executar, i el resultat real és que **el framework 4.5.1 no pot arribar-hi**.

### 15.1 Congelació de la font

- `CERTIFICATION_SOURCE_COMMIT = b21f80d6443e663d95268d3f7f3b9b86d8f23db7`
  (pare `4830b32490b687da541e8b7270ead252dd5428fe`), branca `main`.
- Contracte de congelació: la font de producte i de proves queda congelada al
  commit; els artefactes de verificació (`docs/operations/*`, `.certification/*`)
  són additius i no modifiquen producte ni proves. `IMP` s'ancora explícitament
  al commit congelat perquè el framework no ofereix cap camí `VERIFY_ONLY`
  executat (vegeu 15.3).
- Arbre brut resolt i classificat abans de congelar: PRODUCT (`src/api/post_crq_audit.py`,
  `src/web-app/package.json`, `playwright-smoke.mjs`), TEST (7 fitxers pytest + 4 vitest),
  DOC (`README.md`, runbook), DEVAGENT_STATE (`.gitignore`: `.devagent/`, `.da/`,
  `.devagent.pre-framework-audit/`, `.freebuff/`, `*.db-journal|wal|shm`),
  EVIDENCE (`docs/operations/devagent-evidence/*`), GENERATED (journal eliminat).
  No s'ha committit cap caché, `node_modules`, venv, DB de test ni secret.

### 15.2 Espai de treball local de certificació

`C:\dev\dashboard-e13bd-cert` (NTFS local, fora d'OneDrive, Dropbox o xarxa):
clon del commit congelat, `git status --porcelain` buit, 284 fitxers versionats,
cap `dist/`, `node_modules/` ni `.devagent/` provinent de l'checkout original.

- Python 3.14.3, `py -m venv .venv`, `pip install -r requirements.txt` → exit 0,
  106 paquets en 368 s (únic drift respecte de l'entorn canònic: `pandas 3.0.6`
  vs `3.0.5`; la resta de 105 paquets idèntics).
- Node 24.16.0 / npm 11.13.0, `npm ci` → exit 0, 668 paquets en 104 s.
- `devagent init . --name "Dashboard E13BD" --execution-mode GOVERNED_AUTONOMOUS`
  → `ok=true`, `project_id=dashboard-e13bd-2695770f` (idèntic a l'checkout
  original: la identitat és de nom+fingerprint, no de ruta), `required >=4.5`
  → COMPATIBLE, `framework_copied=false`.
- `devagent project-doctor .` → `all_ok=true`, `boundary_status=OK`,
  `declaration_pollution=0`, `files_seen=284`, 10 exclusions
  (CACHE/DEPENDENCY/TOOL_STATE/GENERATED: `__pycache__`, `.venv` via `pyvenv.cfg`,
  `node_modules` via marker npm, `.git`, `.devagent`, `dist`),
  `orphan_reservations.count=0`.
- Únic efecte col·lateral del framework sobre la font: `devagent init` afegeix
  el seu bloc d'ignorats de runtime a `.gitignore` (redundant amb la política
  del repositori); es restaura perquè l'arbre quedi exactament al commit.

### 15.3 Run governat `VERIFY_ONLY`: resultat real

```
devagent run "<goal de verificació>" . --intent VERIFY_ONLY --json
```

| run | v1 (commit 4830b32) | v2 (commit b21f80d) |
|---|---|---|
| run_id | `RUN-900A6F47276C4B45` | `RUN-A788645E738C4D46` |
| intent classificat | `VERIFY_ONLY` (EXPLICIT) | `VERIFY_ONLY` (EXPLICIT) |
| intent executat | `AUDIT_ONLY` | `AUDIT_ONLY` |
| terminal_state | `AUDITED` (SUCCESS) | `AUDITED` (SUCCESS) |
| claimed | `DISCOVERED, AUDITED` | `DISCOVERED, AUDITED` |
| not_claimed | `IMPLEMENTING, IMPLEMENTED, TESTED, E2E_VERIFIED, INDEPENDENTLY_VERIFIED, CERTIFIED` | idem |
| product_files_modified | 0 | 0 |
| durada | 4 s | 4 s |

**Defecte del framework (no del projecte)**: `IntentContract.VERIFY_ONLY`
declara `terminal_state=INDEPENDENTLY_VERIFIED`, `required_states` fins a
`INDEPENDENTLY_VERIFIED` i `a6_gate_required=True`, però `cmd_run`
(`devagent.py:597-631`) envia **tota** intenció no mutadora a la branca de només
lectura, i el darrer `else` d'aquesta branca (`else:  # AUDIT_ONLY`) executa
l'auditoria brownfield i termina a `AUDITED`. La intenció demanada queda
registrada al rebut de terminalització, però el cicle
`TESTED → E2E_VERIFIED → INDEPENDENTLY_VERIFIED → CERTIFIED` no és assolible
per cap via del CLI 4.5.1.

Dos defectes addicionals, demostrats empíricament (vegeu 15.4):

1. `core/phase4/test_orchestrator.py` només carrega mòduls `unittest` amb glob
   de `test_*.py` **a l'arrel**; el contracte del projecte és pytest amb
   `testpaths=tests` (`pytest.ini`). Un run governat veu 0 proves → A6 fa
   fail-closed (correcte) i el run queda `BLOCKED`.
2. `core/phase4/engineering_orchestrator.py` fa les transicions
   `INDEPENDENTLY_VERIFIED` i `CERTIFIED` **incondicionalment**, sense invocar
   cap verificador, i el CLI hi injecta un `e2e_check` stub
   (`lambda: (0, "one-shot: no e2e fixture declared")`) que es tracta com a E2E
   superat. El verificador independent real
   (`core/autonomy/independent_verifier.py`, `evidence_authority.py`,
   `traceability.py`, cablejats a `ValidationCoordinator`/`factory_runtime`) no
   és abastable des del CLI.

### 15.4 Controls negatius de fals èxit (A6)

Projectes de control a `output/devagent-controls/` (fora del candidat):

| control | run_id | exit | estat | motiu |
|---|---|---|---|---|
| 0 proves executables | `RUN-48605E66EADF49D1` | 1 | `BLOCKED` | `testing blocked: zero tests executed (A6 fake-PASS rejected)` |
| suite executada que falla | `RUN-FD2CB5F6380C450E` | 1 | `BLOCKED` | `testing blocked: executed suite failed` |
| 1 test trivial + `e2e_check` stub | `RUN-248573DB01424FE9` | 0 | `CERTIFIED` | `state=CERTIFIED`, `stages.e2e.observed="one-shot: no e2e fixture declared"`, cap verificador → **vector de fals èxit obert al framework** |

A6 funciona (cap prova executada no pot ser `TESTED`), i alhora queda demostrat
que un rebut `CERTIFIED` del framework no és per si mateix prova de res.

### 15.5 Proves del candidat a l'espai net

| porta | comanda canònica | exit | resultat | durada | log (sha256) |
|---|---|---|---|---|---|
| backend | `.venv/Scripts/python.exe -m pytest -q` (`testpaths=tests`) | 0 | **250 passed, 0 failed** | 401 s | `backend_pytest_v2.log` `831257fb…eb75` |
| frontend | `npm test` (`vitest run`) | 0 | **26/26 fitxers, 79/79 tests** | 64 s | `fe_vitest_v2.log` `41593558…6b18` |
| build | `npm run build` (`vite build`) | 0 | `dist/` generat | 44 s | `fe_build_v2.log` `3b930777…567a` |
| E2E | `npm run smoke:ui` (Playwright, SPA construïda, API mockada) | 0 | `smoke success` | 40 s | `fe_smoke_v2.log` `211497c4…2dd5` |
| residu SQLite | `src/db` abans/després | — | `*.db`, `-journal`, `-wal`, `-shm` = 0 | — | `backend_pytest_v2.log` |

Nota d'hermeticitat: 4 proves de backend i 1 de frontend fallaven en un checkout
pristí per dependre de l'entorn del desenvolupador (Oracle Instant Client
obligatori via `ensure_oracle_thick_mode`, `config/Cadena_conexions.txt` local,
i un `testTimeout` de 15 s superat quan tota la suite vitest corre en paral·lel).
S'han reparat injectant dobles exactament com ja feien les proves germanes i
declarant el pressupost de temps del test pesat; cap expectativa s'ha debilitat.
Prova d'hermeticitat: les 20 proves afectades passen amb `instantclient/`
**amagat** (17,7 s). El re-run complet posterior dona 250/250.

### 15.6 Verificació independent

`docs/operations/devagent-evidence/independent_verifier.py` és l'autoritat de
verificació separada de l'executor (i separada del CLI, que no l'exposa):
re-deriva la congelació, el boundary, els runs, els rebuts i el residu des de
zero, i **re-executa** ella mateixa la suite de frontend i el smoke d'E2E.

Resultat: **14/15 comprovacions PASS**, `informational_findings=[CHK-08B]`,
`blockers=2` (els defectes del framework) → `CERTIFICATION_STATUS=NOT_CERTIFIED`,
`report_sha256=e69f020346d164e66ffefb2b3c7b3196c426fff57ba9ca9974a2a82d807569ad`.

Comprovat de manera independent: `git HEAD` = commit congelat amb arbre net;
`all_ok=true` i `declaration_pollution=0` (project-doctor executat en viu pel
verificador); 250/0 proves de backend; 26/79 de frontend reproduïdes pel
verificador; `dist/index.html` `39fe5730…324d`; smoke reproduït; 0 residu SQLite;
cap fitxer no declarat a l'espai; secrets ignorats i mai versionats; 3 runs amb
**exactament una** terminalització cadascun i 0 orfes; rebuts d'auditoria
**auto-validants** (`receipt_digest` recalculat = registrat) i amb
`product_fingerprint_before == after`; rebuts de terminalització també
auto-validants.

### 15.7 Traçabilitat

`docs/operations/devagent-evidence/traceability_v2.json`:

- cadena de producte `REQ → ACC → ARCH → WP → IMP → TEST → EXEC → EVID → VERIFIER`:
  **9/9 COMPLETE (100%)**, tots els artefactes referenciats existeixen.
- cadena de certificació del framework `TESTED → E2E_VERIFIED →
  INDEPENDENTLY_VERIFIED → CERTIFIED`: **0/5 COMPLETE**, cada enllaç marcat
  `BLOCKED` amb `blocker_class=FRAMEWORK_DEFECT` i referència al codi font
  (`devagent.py:597-631`, `test_orchestrator.py`, `engineering_orchestrator.py`
  passos 10-11). Cap enllaç sintètic.

### 15.8 Estat de certificació

`CERTIFICATION_STATUS = NOT_CERTIFIED` — i és el resultat correcte, no una
manca de feina:

- totes les portes mesurables del producte passen (congelació, boundary,
  250/250 backend, 79/79 frontend, build, E2E dins l'abast declarat, residu 0,
  espai net, seguretat, terminalització, orfes 0, evidència, traçabilitat de
  producte, verificador independent);
- cap run del framework pot reclamar `TESTED`/`E2E_VERIFIED`/
  `INDEPENDENTLY_VERIFIED`/`CERTIFIED` per a aquest projecte, i el framework
  demostra que pot emetre un `CERTIFIED` sense E2E ni verificador. Certificar
  aquí seria precisament el fals èxit que el propi framework prohibeix.

Abast limitat explícitament: `smoke:ui:retal`/`smoke:ui:oracle` (validació
Oracle real) **no** són una porta obligatòria d'aquesta certificació i no s'han
executat: requereixen credencials i base de dades Oracle reals →
`OPTIONAL_EXTERNAL_VALIDATION`, gate humà.

### 15.9 Reproducció

```powershell
git clone "<checkout original>" C:\dev\dashboard-e13bd-cert
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
cd src\web-app; npm ci; cd ..\..
devagent init . --name "Dashboard E13BD" --execution-mode GOVERNED_AUTONOMOUS
devagent project-doctor . --json
devagent run "Verify the frozen release candidate end-to-end" . --intent VERIFY_ONLY --json
.venv\Scripts\python.exe -m pytest -q
cd src\web-app; npm test; npm run build; npm run smoke:ui
```
Per a la verificació independent, des de l'checkout original:

```powershell
py docs/operations/devagent-evidence/independent_verifier.py `
  --workspace C:/dev/dashboard-e13bd-cert `
  --logs <directori de logs> --controls <logs dels controls> `
  --expected-commit b21f80d6443e663d95268d3f7f3b9b86d8f23db7 `
  --ledger docs/operations/devagent-evidence/traceability_v2.json `
  --out <directori de logs>/VERIFICATION_REPORT.json --rerun-fast
```

### 15.10 Portes P0/P1/P2 actualitzats

- P0: cap. (`RISK-006` segueix requerint decisió humana de rotació, però no
  bloqueja: mai versionat, ignorat per `*.bak`, i no és material duplicat
  innecessari perquè pot ser l'única còpia local de les claus.)
- P1: defectes del framework (enrutament `VERIFY_ONLY`, TEST només unittest a
  l'arrel, transició `CERTIFIED` no guardada, `e2e_check` stub) — cal
  corregir-los a DEV Agent, no al producte; `requirements.txt` sense pins;
  CI absent (`GAP-002`).
- P2: 3 fitxers llegats amb rutes absolutes de host (`src/api/fix_mojibake.py`,
  `src/core/import_checks_from_md.py`, `tests/verify_pdf_refinement.py` i
  germans a `archive/`/`scripts/`); `src/db/_probe.db` i
  `src/db/internal_fallback.db` (0 bytes) fora de control de versions;
  declarar entrypoint Python per tal que `ENTRYPOINTS` inclogui
  `src/api/main.py` (`app=FastAPI(...)`, `run.ps1`
  `uvicorn src.api.main:app --host 127.0.0.1 --port 8000`).

### 15.11 Evidència del tancament

- `docs/operations/devagent-evidence/traceability_v2.json` — cadena completa amb
  estats i artefactes.
- `docs/operations/devagent-evidence/independent_verifier.py` — autoritat de
  verificació (reproduïble).
- `docs/operations/devagent-evidence/VERIFICATION_REPORT.json` — informe del
  verificador (`report_sha256=e69f0203…69ad`).
- `docs/operations/devagent-evidence/CERTIFICATION_EVIDENCE.sha256` — inventari
  SHA-256 dels logs d'execució, dels controls i dels JSON de l'checkout net.
- Espai net: `.certification/` (informe + ledger) i `.devagent/evidence/RUN-A788645E738C4D46/`
  (12 artefactes + rebut auto-validant).
