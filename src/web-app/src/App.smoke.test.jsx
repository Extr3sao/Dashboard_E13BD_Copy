import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import App from './App.jsx';
import axios from 'axios';
import { useState } from 'react';

vi.mock('./views/DatabaseAuditWorkspace.jsx', () => ({
  default: function DatabaseAuditWorkspaceMock({ databaseAuditSubtab, setDatabaseAuditSubtab }) {
    const [postCrqConfigOpen, setPostCrqConfigOpen] = useState(false);
    const [postCrqPlannerOpen, setPostCrqPlannerOpen] = useState(false);
    const [postCrqCriticalityOpen, setPostCrqCriticalityOpen] = useState(false);
    const [postCrqExecuted, setPostCrqExecuted] = useState(false);

    return (
      <>
        <div className="flex flex-wrap gap-3">
          {[
            'AnÃ lisi obsolets',
            "Repositori d'obsolets",
            'Auditoria de canvis',
            'Automatitzacions',
            'Tasques i regles',
            'GestiÃ³ de controls',
            'ConfiguraciÃ³ del servidor',
            'Guia i Ajuda',
          ].map((tab) => (
            <button key={tab} type="button" onClick={() => setDatabaseAuditSubtab(tab)}>
              {tab}
            </button>
          ))}
        </div>

        {databaseAuditSubtab === 'AnÃ lisi obsolets' && (
          <section>
            <h3>Anàlisi 360</h3>
            <button type="button">Auditar</button>
          </section>
        )}

        {databaseAuditSubtab === 'Auditoria de canvis' && (
          <section>
            <h3>Control de qualitat post-CRQ</h3>
            <label>
              Base de dades
              <select defaultValue="E13DB">
                <option value="E13DB">E13DB</option>
              </select>
            </label>
            <label>
              Temporalitat
              <select defaultValue="weekly">
                <option value="weekly">setmanal</option>
              </select>
            </label>
            <label>
              Variant
              <select defaultValue="all">
                <option value="all">all</option>
              </select>
            </label>
            <button type="button" onClick={() => setPostCrqConfigOpen((value) => !value)}>
              Obrir configuració
            </button>
            {postCrqConfigOpen && <div>Submenú de configuració</div>}
            <button type="button" onClick={() => setPostCrqPlannerOpen((value) => !value)}>
              Planificador d'execució
            </button>
            {postCrqPlannerOpen && (
              <div>
                <div>Risc del pla:</div>
                <div>Segur</div>
                <div>Prudent</div>
                <div>Agressiu</div>
              </div>
            )}
            <button type="button" onClick={() => setPostCrqCriticalityOpen((value) => !value)}>
              Criticitat de les consultes
            </button>
            {postCrqCriticalityOpen && <div>Cada check es pot reclassificar</div>}
            <button type="button">CHECK_01</button>
            <button type="button" onClick={() => setPostCrqExecuted(true)}>
              Executar
            </button>
            {postCrqExecuted && (
              <div>
                <div>Paràmetres d'execució</div>
                <div>Resum executiu per lots</div>
                <div>Lot prioritzat</div>
                <div>Acció inicial:</div>
                <div>Checks afectats</div>
              </div>
            )}
          </section>
        )}

        {databaseAuditSubtab === 'Automatitzacions' && (
          <section>
            <div>Programació</div>
            <div>Jobs d'automatització</div>
            <label>Nom del job<input defaultValue="Job test" /></label>
          </section>
        )}

        {databaseAuditSubtab === 'Tasques i regles' && (
          <section>
            <div>Regles globals</div>
            <div>Safata interna de tasques</div>
          </section>
        )}

        {databaseAuditSubtab === 'ConfiguraciÃ³ del servidor' && (
          <section>
            <div>Servidor de Correu (SMTP)</div>
            <input defaultValue="tic@example.com" />
          </section>
        )}

        {databaseAuditSubtab === "Repositori d'obsolets" && (
          <section>
            <div>Registre d'Obsolets (SQLite)</div>
          </section>
        )}

        {databaseAuditSubtab === 'Guia i Ajuda' && (
          <section>
            <div>Tutorial</div>
            <h3>Arquitectura</h3>
          </section>
        )}
      </>
    );
  },
}));

vi.mock('axios', () => {
  return {
    default: {
      get: vi.fn((url) => {
        if (url.includes('/api/profiles')) {
          return Promise.resolve({ data: { profiles: ['E13DB'], default: 'E13DB' } });
        }
        if (url.includes('/api/snapshots/latest')) {
          return Promise.resolve({ data: { snapshot: { snapshot_id: 'snapshot_test.parquet', created_at: '2026-02-15T00:00:00', rows_estimated: 1 } } });
        }
        if (url.includes('/api/obsolets')) {
          return Promise.resolve({ data: { items: [], page: { limit: 200, offset: 0 } } });
        }
        if (url.includes('/api/config/openrouter')) {
          return Promise.resolve({ data: { configured: false } });
        }
        if (url.includes('/api/config')) {
          return Promise.resolve({ data: { available_models: ['google/gemini-2.0-flash-exp:free'], current_model: 'google/gemini-2.0-flash-exp:free' } });
        }
        if (url.includes('/api/automation/jobs')) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes('/api/automation/runs')) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes('/api/automation/tasks')) {
          return Promise.resolve({ data: { items: [] } });
        }
        if (url.includes('/api/automation/severity-rules')) {
          return Promise.resolve({
            data: {
              items: [
                {
                  id: 1,
                  severity: 'ALT',
                  create_task: true,
                  task_priority: 'high',
                  send_email: false,
                  attach_report: true,
                  recipients: [],
                  conditions: { min_findings: 1 },
                  enabled: true,
                },
              ],
            },
          });
        }
        if (url.includes('/api/automation/delivery-config')) {
          return Promise.resolve({
            data: {
              smtp_host: 'smtp.local',
              smtp_port: 587,
              smtp_username: 'demo',
              smtp_password: 'secret',
              smtp_use_tls: true,
              from_email: 'oracle-audit@example.com',
              default_recipients: ['dba@example.com'],
            },
          });
        }
        if (url.includes('/api/automation/delivery-routes')) {
          return Promise.resolve({
            data: {
              tic_summary_recipients: ['tic@example.com'],
              providers: [{ provider_code: 'LOT_APP', label: 'Aplicacions', emails: ['app@example.com'], enabled: true }],
            },
          });
        }
        if (url.includes('/api/knowledge')) {
          return Promise.resolve({ data: [] });
        }
        if (url.includes('/api/audit/post-crq/checks')) {
          return Promise.resolve({
            data: {
              checks: [
                {
                  check_id: 'CHECK_01',
                  title: 'TAULES RECENTS SENSE PRIMARY KEY',
                  severitat: 'Mitjà',
                  criticitat: 'Mitjà',
                  criteri: 'Només taules modificades recentment',
                },
                {
                  check_id: 'CHECK_03',
                  title: 'SEQÜÈNCIES RECENTS SENSE CACHE O AMB CACHE INSUFICIENT',
                  severitat: 'Crític',
                  criticitat: 'Crític',
                  criteri: 'Només seqüències modificades recentment',
                },
                {
                  check_id: 'CHECK_04',
                  title: 'FOREIGN KEYS RECENTS SENSE ÍNDEX DE SUPORT',
                  severitat: 'Crític',
                  criticitat: 'Crític',
                  criteri: 'Només foreign keys modificades recentment',
                },
              ],
            },
          });
        }
        return Promise.resolve({ data: {} });
      }),
      post: vi.fn((url) => {
        if (url.includes('/api/audit/dashboard-stats')) {
          return Promise.resolve({
            data: {
              total_gb: 0,
              recovered_gb: 0,
              distribution: [0, 0, 0, 0, 0],
              status_counts: { CRITIC: 0, RISC: 0, OK: 0 },
              apex_total: 0,
              top_candidates: [],
            },
          });
        }
        if (url.includes('/api/db/add')) {
          return Promise.resolve({ data: { status: 'success' } });
        }
        if (url.includes('/api/snapshots/query')) {
          return Promise.resolve({
            data: {
              snapshot_id: 'snapshot_test.parquet',
              rows: [],
              summary: { total_objects: 0, total_gb: 0, avg_score: 0, drop_count: 0 },
              facets: { schemas: [], recommendations: [] },
              page: { limit: 1000, offset: 0 },
            },
          });
        }
        if (url.includes('/api/audit/post-crq/run')) {
          return Promise.resolve({
            data: {
              audit_type: 'post_crq',
              context: {
                profile: 'E13DB',
                schemas: ['APP_USER'],
                time_filter: { mode: 'preset', preset: 'weekly', days_back: 7 },
                source_file: 'auditoria_post_crq.md',
              },
              summary: {
                selected_checks: 1,
                executed_checks: 1,
                checks_with_findings: 1,
                total_findings: 1,
                checks_with_errors: 0,
                findings_by_criticality: { 'Crític': 0, 'Mitjà': 1, 'Baix': 0 },
                criticality_sections: [
                  { criticality_key: 'CRITIC', criticality_label: 'Crític', action_text: "Aquestes incidències s'han de solucionar de manera urgent.", items: [] },
                  { criticality_key: 'MITJA', criticality_label: 'Mitjà', action_text: "Aquestes incidències s'han de solucionar en un termini màxim de 15 dies.", items: [{ check_id: 'CHECK_01', summary_text: "S'han trobat 1 taula dels esquemes APP_USER sense primary key." }] },
                  { criticality_key: 'BAIX', criticality_label: 'Baix', action_text: "Aquestes incidències s'han de solucionar en un termini màxim d'1 mes.", items: [] },
                ],
                detected_time_range: { start_at: '2026-03-08 10:00', end_at: '2026-03-08 10:00' },
                environment_message: 'Corregir urgentment!!!',
              },
              report_model: {
                agent_runtime: {
                  orchestrator: 'orchestrator-e13bd',
                  architect: 'architect-e13bd',
                  dba: 'dba-e13bd',
                  developer: 'developer-e13bd',
                  tester: 'tester-e13bd',
                  reporting: 'insights-reporting-e13bd',
                  phases: [
                    { id: 'context', lead: 'orchestrator-e13bd', validators: ['architect-e13bd'] },
                    { id: 'reporting', lead: 'insights-reporting-e13bd', validators: ['tester-e13bd'] },
                  ],
                },
                criticality_blocks: [
                  { criticality_key: 'CRITIC', criticality_label: 'Crític', action_text: "Aquestes incidències s'han de solucionar de manera urgent.", items: [] },
                  {
                    criticality_key: 'MITJA',
                    criticality_label: 'Mitjà',
                    action_text: "Aquestes incidències s'han de solucionar en un termini màxim de 15 dies.",
                    items: [
                      {
                        check_id: 'CHECK_01',
                        title: 'TAULES RECENTS SENSE PRIMARY KEY',
                        summary_text: "S'han detectat taules dels esquemes APP_USER sense primary key.",
                        top_examples: [{ schema: 'APP_USER', object_name: 'TMP_EXAMPLE', lot: 'LOT_APP', responsable: 'No assignat' }],
                      },
                    ],
                  },
                  { criticality_key: 'BAIX', criticality_label: 'Baix', action_text: "Aquestes incidències s'han de solucionar en un termini màxim d'1 mes.", items: [] },
                ],
                critical_incident_cards: [],
                quality_gate: { status: 'ok', issues: [], critical_without_lot: 0 },
                execution_parameters: {
                  profile: 'E13DB',
                  generated_at: '2026-03-08 10:00',
                  time_window: { start_at: '2026-03-08 10:00', end_at: '2026-03-08 10:00' },
                },
                lot_summary: [
                  {
                    lot: 'LOT_APP',
                    critical: 0,
                    medium: 1,
                    low: 0,
                    checks: ['CHECK_01'],
                    check_descriptions: [{ check_id: 'CHECK_01', title: 'TAULES RECENTS SENSE PRIMARY KEY' }],
                    schemas: ['APP_USER'],
                    affected_objects: 1,
                    first_action: "Crear la PRIMARY KEY o justificar documentalment l'excepció.",
                    dominant_impact: "Risc d'integritat i dificultat de manteniment.",
                    priority: 'Mitjà',
                  },
                ],
                lot_incident_groups: [
                  {
                    lot: 'LOT_APP',
                    check: 'CHECK_01',
                    title: 'TAULES RECENTS SENSE PRIMARY KEY',
                    description: "S'ha detectat una taula sense PRIMARY KEY activa.",
                    severity: 'Mitjà',
                    termini_dies: 15,
                    impacte: "Complica la integritat i el manteniment del model.",
                    accio_recomanada: "Crear la PRIMARY KEY o justificar documentalment l'excepció.",
                    validacio_posterior: 'Reexecutar el check i validar la unicitat de les dades.',
                    schemas: [
                      {
                        nom: 'APP_USER',
                        object_count: 1,
                        objectes: [
                          {
                            OBJECTE: 'TMP_EXAMPLE',
                            TIPUS: 'TABLE',
                            'DADA TÈCNICA': 'Sense PK activa · volum baix',
                          },
                        ],
                      },
                    ],
                  },
                ],
              final_observations: {
                blocking_errors: [],
                warnings: [],
                next_steps: ["Aplicar la correcció i reexecutar l'auditoria."],
              },
              },
              report_options: { include_annex: true },
              executed_checks: [
                {
                  check_id: 'CHECK_01',
                  title: 'TAULES RECENTS SENSE PRIMARY KEY',
                  severitat: 'Mitjà',
                  criticitat: 'Mitjà',
                  status: 'ok',
                  row_count: 1,
                },
              ],
              results_by_check: [
                {
                  check_id: 'CHECK_01',
                  title: 'TAULES RECENTS SENSE PRIMARY KEY',
                  severitat: 'Mitjà',
                  criticitat: 'Mitjà',
                  status: 'ok',
                  row_count: 1,
                  columns: ['ESQUEMA', 'TAULA'],
                  rows: [{ ESQUEMA: 'APP_USER', TAULA: 'TMP_EXAMPLE' }],
                },
              ],
              errors: [],
            },
          });
        }
        if (url.includes('/api/automation/jobs/')) {
          return Promise.resolve({ data: { status: 'started' } });
        }
        if (url.includes('/api/automation/jobs')) {
          return Promise.resolve({ data: { id: 1, name: 'Job test' } });
        }
        if (url.includes('/api/automation/severity-rules')) {
          return Promise.resolve({ data: { id: 2, severity: 'MITJA' } });
        }
        if (url.includes('/api/automation/delivery-config/test-email')) {
          return Promise.resolve({ data: { status: 'success', message: 'Correu de prova enviat' } });
        }
        return Promise.resolve({ data: {} });
      }),
      put: vi.fn(() => Promise.resolve({ data: {} })),
      delete: vi.fn(() => Promise.resolve({ data: { status: 'success' } })),
    },
  };
});

describe('App smoke tests', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  async function openDatabaseAuditSubtab(name) {
    const databaseAuditTab = await screen.findByRole('button', { name: 'Auditoria BBDD' });
    fireEvent.click(databaseAuditTab);
    fireEvent.click(await screen.findByRole('button', { name }));
  }

  test('T1: render inicial sense pantalla negra', async () => {
    render(<App />);

    expect(await screen.findByText('Oracle Audit')).toBeInTheDocument();
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalled();
    });
  });

  test('T2: pestanya Auditoria BBDD mostra botó Auditar a obsolets', async () => {
    render(<App />);

    expect(await screen.findByRole('button', { name: /Auditar/i })).toBeInTheDocument();
    expect(await screen.findByText(/Anàlisi 360/i)).toBeInTheDocument();
  });

  test('T2b: subpestanya Auditoria de canvis renderitza checks post-CRQ', async () => {
    render(<App />);

    await openDatabaseAuditSubtab('Auditoria de canvis');

    expect(await screen.findByText(/Control de qualitat post-CRQ/i, {}, { timeout: 5000 })).toBeInTheDocument();
    expect((await screen.findAllByText('CHECK_01')).length).toBeGreaterThan(0);
    expect(await screen.findByText('Base de dades')).toBeInTheDocument();
    expect((await screen.findAllByRole('combobox')).length).toBeGreaterThan(2);
    expect(await screen.findByText(/Temporalitat/i)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /Obrir configuració/i })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: /Obrir configuració/i }));
    expect(await screen.findByText(/Submenú de configuració/i)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /Planificador d'execució/i })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: /Planificador d'execució/i }));
    expect(await screen.findByText(/Risc del pla:/i)).toBeInTheDocument();
    expect((await screen.findAllByText(/Segur|Prudent|Agressiu/i)).length).toBeGreaterThan(0);
    expect(await screen.findByRole('button', { name: /Criticitat de les consultes/i })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: /Criticitat de les consultes/i }));
    expect(await screen.findByText(/Cada check es pot reclassificar/i)).toBeInTheDocument();
    expect((await screen.findAllByDisplayValue('E13DB')).length).toBe(1);
  });

  test('T2e: resultat post-CRQ mostra resum operatiu per lots en pantalla', async () => {
    render(<App />);

    await openDatabaseAuditSubtab('Auditoria de canvis');

    fireEvent.click(await screen.findByText('CHECK_01'));
    fireEvent.click(await screen.findByRole('button', { name: /Executar/i }));

    expect(await screen.findByText(/Paràmetres d'execució/i)).toBeInTheDocument();
    expect((await screen.findAllByText(/Resum executiu per lots/i)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/Lot prioritzat/i)).length).toBeGreaterThan(0);
    expect(await screen.findByText(/Acció inicial:/i)).toBeInTheDocument();
    expect(await screen.findByText(/Checks afectats/i)).toBeInTheDocument();
    expect(screen.queryByText(/Resum IA del CHECK_11/i)).not.toBeInTheDocument();
  });

  test('T2c: subpestanya Automatitzacions renderitza scheduler i SMTP', async () => {
    render(<App />);

    await openDatabaseAuditSubtab('Automatitzacions');

    expect(await screen.findByText(/Programaci/i)).toBeInTheDocument();
    expect(await screen.findByText(/Jobs d'automatització/i)).toBeInTheDocument();
    expect(await screen.findByText(/Nom del job/i)).toBeInTheDocument();
  });

  test('T2d: subpestanya Tasques i regles renderitza regles globals i safata', async () => {
    render(<App />);

    await openDatabaseAuditSubtab('Tasques i regles');

    expect(await screen.findByText(/Regles globals/i)).toBeInTheDocument();
    expect(await screen.findByText(/Safata interna de tasques/i)).toBeInTheDocument();
  });

  test('T3: Configuració del servidor mostra SMTP i rutes', async () => {
    render(<App />);

    await openDatabaseAuditSubtab(/Configuraci. del servidor/i);

    expect(await screen.findByText(/Servidor de Correu \(SMTP\)/i)).toBeInTheDocument();
    expect(await screen.findByDisplayValue('tic@example.com')).toBeInTheDocument();
  });

  test('T4: acció de generar report visible', async () => {
    render(<App />);
    expect(await screen.findByRole('button', { name: 'Generar Informe' })).toBeInTheDocument();
  });

  test('T5: subpestanya Repositori d’obsolets renderitza el registre', async () => {
    render(<App />);

    await openDatabaseAuditSubtab("Repositori d'obsolets");

    expect(await screen.findByText(/Registre d'Obsolets \(SQLite\)/i)).toBeInTheDocument();
  });

  test('T6: subpestanya Guia i Ajuda mostra el tutorial actual', async () => {
    render(<App />);

    await openDatabaseAuditSubtab('Guia i Ajuda');

    expect(await screen.findByText('Tutorial')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Arquitectura' })).toBeInTheDocument();
  });

  test('T7: la pestanya superior Configuració està deshabilitada', async () => {
    render(<App />);

    expect(await screen.findByTitle(/Configuraci. deshabilitada/i)).toBeDisabled();
  });
});




