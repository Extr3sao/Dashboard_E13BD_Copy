import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import AutomationView from './AutomationView.jsx';
import MailConfigView from './MailConfigView.jsx';
import {
  createAutomationJob,
  enqueueRetry,
  listAutomationChangeEvents,
  listAutomationRunLotsFiltered,
  listAutomationRuns,
  listRetryQueue,
  runRetryNow,
  updateDeliveryTemplates,
  updateLotRoutes,
  updateSchemaLots,
} from '../api/automation.js';

vi.mock('../components/AutomationGuide.jsx', () => ({
  default: () => (
    <div>
      <h1>Guia d'Automatitzacions</h1>
      <p>Flux recomanat</p>
    </div>
  ),
}));

vi.mock('../api/automation.js', () => ({
  applyMasterLotsBackfill: vi.fn(() => Promise.resolve({ id: 10, items: [] })),
  createAutomationJob: vi.fn(() => Promise.resolve({ id: 1 })),
  deleteAutomationJob: vi.fn(() => Promise.resolve({ status: 'success' })),
  exportAutomationAnalyticsMonthlyPdf: vi.fn(() => Promise.resolve({ data: '', headers: { 'content-type': 'application/pdf' } })),
  getAutomationRunReportUrl: vi.fn(() => '/api/automation/runs/1/report'),
  getAutomationAnalyticsOverview: vi.fn(() => Promise.resolve({ runs: 0, total_findings: 0, lots_with_findings: 0, checks_with_errors: 0 })),
  getAutomationMaintenanceSummary: vi.fn(() => Promise.resolve({ auto_purge_enabled: true, history_retention_days: 30, retry_retention_days: 15 })),
  getDeliveryRoutes: vi.fn(() => Promise.resolve({
    tic_summary_recipients: ['tic@example.com'],
    providers: [
      { provider_code: 'LOT_APP', label: 'Aplicacions', emails: ['app@example.com'], enabled: true },
      { provider_code: 'TIC', label: 'ATIC', emails: ['tic.area@example.com', 'tic.alt@example.com'], enabled: true },
      { provider_code: 'PROVES', label: 'Proves', emails: ['franciscovalladares@gencat.cat'], enabled: true },
    ],
  })),
  listAutomationAnalyticsChecks: vi.fn(() => Promise.resolve({ items: [] })),
  listAutomationAnalyticsLots: vi.fn(() => Promise.resolve({ items: [] })),
  listAutomationAnalyticsSchemas: vi.fn(() => Promise.resolve({ items: [] })),
  getDeliveryConfig: vi.fn(() => Promise.resolve({
    smtp_host: 'smtp.local',
    smtp_port: 587,
    smtp_username: 'demo',
    smtp_password: 'secret',
    smtp_use_tls: true,
    from_email: 'oracle-audit@example.com',
    default_recipients: ['dba@example.com'],
    failure_notification_recipients: ['suport@example.com'],
    auto_purge_enabled: true,
    history_retention_days: 30,
    retry_retention_days: 15,
    last_auto_purge_at: '2026-03-21T01:00:00Z',
  })),
  listAutomationChangeEvents: vi.fn(() => Promise.resolve({ items: [] })),
  listAutomationJobs: vi.fn(() => Promise.resolve({ items: [] })),
  listAutomationRuns: vi.fn(() => Promise.resolve({ items: [] })),
  listMasterLotBackfillRuns: vi.fn(() => Promise.resolve({ items: [] })),
  listMasterLots: vi.fn(() => Promise.resolve({ items: [{ code: 'LOT_APP', label: 'Aplicacions', description: '', enabled: true }] })),
  listSchemaLots: vi.fn(() => Promise.resolve({ items: [{ schema_name: 'APP_USER', lot_name: 'LOT_APP' }] })),
  listDeliveryTemplates: vi.fn(() => Promise.resolve({
    items: [
      { template_key: 'job_generation_failure', audience: 'failure', subject_template: 'Error', body_template: 'Cos error', enabled: true },
      { template_key: 'provider_with_findings', audience: 'provider', subject_template: 'Assumpte', body_template: 'Cos', enabled: true },
      { template_key: 'tic_summary', audience: 'tic', subject_template: 'Resum', body_template: 'Cos TIC', enabled: true },
      { template_key: 'manual_resend', audience: 'retry', subject_template: 'Reenviament', body_template: 'Cos retry', enabled: true },
    ],
  })),
  listLotRoutes: vi.fn(() => Promise.resolve({ items: [{ lot_code: 'LOT_APP', audience: 'provider', label: 'Aplicacions', emails: ['app@example.com'], enabled: true }] })),
  listRetryQueue: vi.fn(() => Promise.resolve({ items: [] })),
  previewMasterLotsBackfill: vi.fn(() => Promise.resolve({ id: 10, summary: {}, items: [] })),
  purgeAutomationHistory: vi.fn(() => Promise.resolve({ deleted: 0 })),
  purgeAutomationRetryQueue: vi.fn(() => Promise.resolve({ deleted: 0 })),
  runAutomationJobNow: vi.fn(() => Promise.resolve({ status: 'started' })),
  updateAutomationJob: vi.fn(() => Promise.resolve({ id: 1 })),
  updateDeliveryConfig: vi.fn(() => Promise.resolve({ status: 'success' })),
  updateDeliveryRoutes: vi.fn(() => Promise.resolve({ status: 'success' })),
  updateDeliveryTemplates: vi.fn(() => Promise.resolve({ items: [] })),
  updateLotRoutes: vi.fn(() => Promise.resolve({ items: [] })),
  updateMasterLots: vi.fn(() => Promise.resolve({ items: [] })),
  updateSchemaLots: vi.fn(() => Promise.resolve({ items: [] })),
  enqueueRetry: vi.fn(() => Promise.resolve({ status: 'success' })),
  exportAutomationRunLotsCsv: vi.fn(() => Promise.resolve({ data: '', headers: { 'content-type': 'text/csv' } })),
  getAutomationRunReportData: vi.fn(() => Promise.resolve({
    audit_type: 'post_crq',
    context: {
      profile: 'E13DB',
      schemas: ['APP_USER'],
      time_filter: { mode: 'preset', preset: 'weekly' },
      source_file: 'Auditoria_post_crq.md',
    },
    snapshot_metadata: {
      selected_checks: ['CHECK_01'],
      criticality_overrides: {},
      scheduler_options: { max_concurrency: 2 },
    },
  })),
  listAutomationRunLotsFiltered: vi.fn(() => Promise.resolve({ items: [] })),
  runRetryNow: vi.fn(() => Promise.resolve({ status: 'done' })),
}));

vi.mock('../api/postCrqAudit.js', () => ({
  listPostCrqChecks: vi.fn(() => Promise.resolve({
    checks: [{ check_id: 'CHECK_01', title: 'Check demo', criteri: 'criteri' }],
  })),
}));

async function clickScreenButton(label) {
  await screen.findByText(/Programaci/i);
  const button = screen
    .getAllByText(label)
    .map((node) => node.closest('button'))
    .find(Boolean);
  fireEvent.click(button);
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  window.scrollTo = vi.fn();
  global.IntersectionObserver = class {
    observe() {}
    disconnect() {}
    unobserve() {}
  };
});

test('AutomationView starts on Jobs and lets you switch internal screens', async () => {
  render(<AutomationView profiles={['E13DB']} />);

  expect(await screen.findByText(/Programaci/i)).toBeInTheDocument();
  expect(screen.getAllByText('Jobs').length).toBeGreaterThan(0);
  expect(screen.getByText(/Nom del job/i)).toBeInTheDocument();

  await clickScreenButton('Lots i mapatge');
  expect(await screen.findByText(/Mapeig schema -> lot/i)).toBeInTheDocument();

  await clickScreenButton('Ajuda');
  expect(await screen.findByText(/Guia d'Automatitzacions/i)).toBeInTheDocument();
});

test('AutomationView shows the distribution job mode and remembers the selected screen', async () => {
  render(<AutomationView profiles={['E13DB']} />);

  expect(await screen.findByText(/Nom del job/i)).toBeInTheDocument();
  fireEvent.change(screen.getByDisplayValue('Auditoria de canvis'), { target: { value: 'post_crq_distribution' } });

  expect(await screen.findByText(/triar l'audiencia real dels correus/i)).toBeInTheDocument();
  expect(screen.getByRole('option', { name: /lots Post-CRQ/i })).toBeInTheDocument();

  await clickScreenButton('Plantilles');
  expect(localStorage.getItem('automationSection')).toBe('templates');
});

test('AutomationView saves distribution delivery targets and override recipients', async () => {
  render(<AutomationView profiles={['E13DB']} />);

  expect(await screen.findByText(/Nom del job/i)).toBeInTheDocument();
  fireEvent.change(screen.getByDisplayValue('Auditoria de canvis'), { target: { value: 'post_crq_distribution' } });
  fireEvent.change(screen.getByRole('textbox', { name: /Nom del job/i }), { target: { value: 'Job proves distribucio' } });

  const deliverySelect = await screen.findByRole('listbox', { name: /Envia correus a/i });
  Array.from(deliverySelect.options).forEach((option) => {
    option.selected = option.value === 'lots' || option.value === 'proves';
  });
  fireEvent.change(deliverySelect);

  fireEvent.change(screen.getByPlaceholderText(/franciscovalladares@gencat.cat/i), {
    target: { value: 'tester@gencat.cat' },
  });
  fireEvent.click(screen.getByRole('button', { name: /Crea job/i }));

  await waitFor(() => {
    expect(createAutomationJob).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Job proves distribucio',
      audit_type: 'post_crq_distribution',
      job_config: expect.objectContaining({
        delivery: {
          targets: ['lots'],
          test_mode: true,
          override_recipients: ['tester@gencat.cat'],
        },
      }),
    }));
  });
});

test('AutomationView saves Post-CRQ scheduler config and always keeps backend base criticality for jobs', async () => {
  render(<AutomationView profiles={['E13DB']} />);

  expect(await screen.findByText(/Nom del job/i)).toBeInTheDocument();
  fireEvent.change(screen.getByRole('textbox', { name: /Nom del job/i }), { target: { value: 'Job post-crq paritat' } });
  fireEvent.change(screen.getByLabelText(/Concurrència global/i), { target: { value: '3' } });

  const checksList = screen.getByRole('listbox', { name: /Checks inclosos/i });
  Array.from(checksList.options).forEach((option) => {
    option.selected = option.value === 'CHECK_01';
  });
  fireEvent.change(checksList);
  expect(screen.queryByText(/Overrides de criticitat/i)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Crea job/i }));

  await waitFor(() => {
    expect(createAutomationJob).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Job post-crq paritat',
      audit_type: 'post_crq',
      scheduler_options: expect.objectContaining({
        max_concurrency: 3,
      }),
      criticality_overrides: {},
    }));
  });
});

test('AutomationView separates TIC summary, special contexts and lot routes in Jobs context', async () => {
  render(<AutomationView profiles={['E13DB']} />);

  expect(await screen.findByText(/Nom del job/i)).toBeInTheDocument();
  const jobSection = document.getElementById('job_form');
  const contextSection = document.getElementById('context');
  const jobsSection = document.getElementById('jobs');
  expect(jobSection.parentElement).toBe(contextSection.parentElement);
  expect(jobSection.parentElement).not.toBe(jobsSection.parentElement);

  const areaTicCard = within(contextSection).getByText(/Destinataris consolidats del resum general/i).closest('div.rounded-2xl');
  const specialContextsCard = within(contextSection).getByText(/Caixes de distribució que no formen part/i).closest('div.rounded-2xl');
  const lotRoutesCard = within(contextSection).getByText(/Totes les rutes per lot disponibles al backend/i).closest('div.rounded-2xl');

  expect(within(areaTicCard).getByText(/Ruta activa:\s*ATIC/i)).toBeInTheDocument();
  expect(within(areaTicCard).getAllByText(/tic@example\.com/i).length).toBeGreaterThan(0);
  expect(within(areaTicCard).getAllByText(/tic\.area@example\.com/i).length).toBeGreaterThan(0);
  expect(within(specialContextsCard).getByText('PROVES')).toBeInTheDocument();
  expect(within(specialContextsCard).queryByText('ATIC')).not.toBeInTheDocument();
  expect(within(lotRoutesCard).getAllByText('LOT_APP').length).toBeGreaterThan(0);
  expect(within(lotRoutesCard).getAllByText(/app@example\.com/i).length).toBeGreaterThan(0);
  expect(within(lotRoutesCard).getByText('Aplicacions')).toBeInTheDocument();
});

test('MailConfigView loads TIC recipients and provider routes', async () => {
  render(<MailConfigView />);

  expect(await screen.findByDisplayValue('tic@example.com')).toBeInTheDocument();
  expect(screen.getByDisplayValue('suport@example.com')).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.getByDisplayValue('LOT_APP')).toBeInTheDocument();
    expect(screen.getByDisplayValue('app@example.com')).toBeInTheDocument();
  });
  expect(screen.getByDisplayValue('30')).toBeInTheDocument();
  expect(screen.getByDisplayValue('15')).toBeInTheDocument();
  expect(screen.getByText(/Darrera purga autom/i)).toBeInTheDocument();
});

test('AutomationView blocks saving duplicated schema mappings', async () => {
  render(<AutomationView profiles={['E13DB']} />);

  await clickScreenButton('Lots i mapatge');
  expect(await screen.findByDisplayValue('APP_USER')).toBeInTheDocument();
  const mappingSection = screen.getByText(/Mapeig schema -> lot/i).closest('section');
  fireEvent.click(within(mappingSection).getByRole('button', { name: /afegeix/i }));

  const schemaInputs = screen.getAllByPlaceholderText(/Schema Oracle/i);
  fireEvent.change(schemaInputs[schemaInputs.length - 1], { target: { value: 'APP_USER' } });

  expect(await screen.findByText(/Schemas duplicats: APP_USER/i)).toBeInTheDocument();
  expect(within(mappingSection).getByRole('button', { name: /Desa mapatge/i })).toBeDisabled();
  expect(updateSchemaLots).not.toHaveBeenCalled();
});

test('AutomationView keeps focus when editing schema mapping rows', async () => {
  render(<AutomationView profiles={['E13DB']} />);

  await clickScreenButton('Lots i mapatge');
  const input = await screen.findByDisplayValue('APP_USER');
  input.focus();
  fireEvent.change(input, { target: { value: 'APP_USER_X' } });

  expect(document.activeElement).toBe(input);
  expect(input).toHaveValue('APP_USER_X');
});

test('AutomationView shows catalan template labels and keeps focus while editing template key', async () => {
  render(<AutomationView profiles={['E13DB']} />);

  await clickScreenButton('Plantilles');
  expect(await screen.findByText(/Error de generació de l'informe/i)).toBeInTheDocument();
  expect((await screen.findAllByText(/Lot amb troballes/i)).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Resum TIC/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Reenviament manual/i).length).toBeGreaterThan(0);

  const templateSection = document.getElementById('templates');
  const templateInput = within(templateSection).getByDisplayValue('provider_with_findings');
  templateInput.focus();
  fireEvent.change(templateInput, { target: { value: 'provider_with_findings_v2' } });

  expect(document.activeElement).toBe(templateInput);
  expect(templateInput).toHaveValue('provider_with_findings_v2');
});

test('AutomationView exposes contextual help for each internal screen', async () => {
  render(<AutomationView profiles={['E13DB']} />);

  fireEvent.click(await screen.findByRole('button', { name: /Ajuda: Jobs d'automatitzaci/i }));
  expect(await screen.findByRole('dialog', { name: /Jobs d'automatitzaci/i })).toBeInTheDocument();
  expect(screen.getByText(/crear o editar jobs programats/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Tanca ajuda/i }));
  await clickScreenButton('Lots i mapatge');
  fireEvent.click(screen.getByRole('button', { name: /Ajuda: Lots i mapatge/i }));

  expect(await screen.findByRole('dialog', { name: /Lots i mapatge/i })).toBeInTheDocument();
  expect(screen.getByText(/Relaciona esquemes amb lots funcionals/i)).toBeInTheDocument();
});

test('AutomationView lets you inspect run history and manage retries', async () => {
  listAutomationRuns.mockResolvedValueOnce({
    items: [{
      id: 77,
      job_id: 9,
      job_name: 'Job setmanal',
      started_at: '2026-03-25T08:00:00Z',
      status: 'partial_error',
      summary: { lot_execution: { with_findings: 1, without_findings: 0, query_errors: 0, unmapped: 0 } },
    }],
  });
  listAutomationRunLotsFiltered.mockResolvedValueOnce({
    items: [{
      lot: 'LOT_APP',
      detection_status: 'CON_HALLAZGOS',
      num_findings: 2,
      delivery_audience: 'provider',
      delivery_result: 'delivery_error',
      report_generated: true,
      email_sent: false,
      observaciones: 'SMTP KO',
    }],
  });
  listRetryQueue.mockResolvedValue({
    items: [{
      id: 501,
      run_id: 77,
      lot: 'LOT_APP',
      audience: 'provider',
      attempt_number: 1,
      retry_mode: 'manual',
      status: 'pending',
      last_error: 'SMTP KO',
    }],
  });

  render(<AutomationView profiles={['E13DB']} />);

  await clickScreenButton('Històric');
  expect(await screen.findByText('Job setmanal')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /^Lots$/i }));
  const historySection = document.getElementById('history');
  expect(await within(historySection).findByText((content, node) => node?.tagName === 'TD' && content === 'LOT_APP')).toBeInTheDocument();
  expect(listAutomationRunLotsFiltered).toHaveBeenCalledWith(77, expect.any(Object));

  fireEvent.click(screen.getByRole('button', { name: /Envia a reintents/i }));
  await waitFor(() => {
    expect(enqueueRetry).toHaveBeenCalledWith({
      run_id: 77,
      lot: 'LOT_APP',
      audience: 'provider',
      requested_by: 'automation_ui',
    });
  });

  await clickScreenButton('Reintents');
  fireEvent.click(await screen.findByRole('button', { name: /^Executa$/i }));
  await waitFor(() => {
    expect(runRetryNow).toHaveBeenCalled();
  });
});

test('AutomationView formats history timestamps in local time instead of showing raw UTC', async () => {
  const toLocaleStringSpy = vi.spyOn(Date.prototype, 'toLocaleString').mockReturnValue('25/03/2026, 09:00:00');
  listAutomationChangeEvents.mockResolvedValueOnce({
    items: [{
      id: 301,
      created_at: '2026-03-25T08:00:00Z',
      entity_type: 'job',
      entity_key: 'setmanal',
      action: 'update',
      actor: 'automation_ui',
      reason: 'Test timestamp',
    }],
  });
  listAutomationRuns.mockResolvedValueOnce({
    items: [{
      id: 78,
      job_id: 9,
      job_name: 'Job local time',
      started_at: '2026-03-25T08:00:00Z',
      status: 'success',
      summary: {},
    }],
  });

  render(<AutomationView profiles={['E13DB']} />);

  await clickScreenButton('Històric');
  expect(await screen.findByText('Job local time')).toBeInTheDocument();
  expect(screen.getAllByText('25/03/2026, 09:00:00').length).toBeGreaterThan(0);
  expect(screen.queryByText('2026-03-25T08:00:00Z')).not.toBeInTheDocument();

  toLocaleStringSpy.mockRestore();
});

test('AutomationView saves lot routes and templates from their dedicated screens', async () => {
  render(<AutomationView profiles={['E13DB']} />);

  await clickScreenButton('Destinataris');
  const routesSection = document.getElementById('lot_routes');
  const lotInput = await within(routesSection).findByPlaceholderText('Lot');
  fireEvent.change(lotInput, { target: { value: 'LOT_APP_X' } });
  fireEvent.click(within(routesSection).getByRole('button', { name: /Desa rutes/i }));
  await waitFor(() => {
    expect(updateLotRoutes).toHaveBeenCalledWith({
      items: [expect.objectContaining({ lot_code: 'LOT_APP_X', audience: 'provider', emails: ['app@example.com'] })],
      actor: 'automation_ui',
    });
  });

  await clickScreenButton('Plantilles');
  const templatesSection = document.getElementById('templates');
  const subjectInput = within(templatesSection).getByDisplayValue('Assumpte');
  fireEvent.change(subjectInput, { target: { value: 'Assumpte revisat' } });
  fireEvent.click(within(templatesSection).getByRole('button', { name: /Desa plantilles/i }));
  await waitFor(() => {
    expect(updateDeliveryTemplates).toHaveBeenCalledWith({
      items: expect.arrayContaining([expect.objectContaining({ subject_template: 'Assumpte revisat' })]),
      actor: 'automation_ui',
    });
  });
});
