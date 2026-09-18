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
