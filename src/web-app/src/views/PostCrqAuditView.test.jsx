import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import PostCrqAuditView from './PostCrqAuditView.jsx';
import { downloadPostCrqReport } from '../api/postCrqAudit.js';

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async () => ({ svg: '<svg />' })),
  },
}));

vi.mock('../api/postCrqAudit.js', () => ({
  downloadPostCrqReport: vi.fn(() => Promise.resolve({
    data: new Blob(['demo']),
    headers: { 'content-disposition': 'attachment; filename=demo.pdf' },
  })),
}));

vi.mock('axios', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: { content: '' } })),
  },
}));

function buildProps() {
  return {
    profiles: ['E13DB'],
    selectedProfile: 'E13DB',
    checksLoading: false,
    checks: [{ check_id: 'CHECK_01', title: 'Check demo', criteri: 'criteri' }],
    selectedChecks: ['CHECK_01'],
    criticalityOverrides: {},
    schedulerOptions: {},
    timeFilter: { mode: 'preset', preset: 'weekly' },
    schemasValue: '',
    isRunning: false,
    result: {
      audit_type: 'post_crq',
      summary: {},
      report_model: {
        lot_summary: [
          { lot: 'LOT_APP', checks: ['CHECK_01'], schemas: ['APP_USER'], priority: 'Mitja' },
          { lot: 'LOT_AUX', checks: ['CHECK_01'], schemas: ['APP_AUX'], priority: 'Alt' },
        ],
        lot_incident_groups: [],
        detail_sections: [],
      },
      executed_checks: [
        {
          check_id: 'CHECK_01',
          title: 'Check demo',
          criticitat: 'Mitja',
          status: 'ok',
          duration_ms: 1200,
          row_count: 3,
        },
      ],
      results_by_check: [
        {
          check_id: 'CHECK_01',
          title: 'Check demo',
          criticitat: 'Mitja',
          status: 'ok',
          duration_ms: 1200,
          row_count: 3,
          columns: ['OBJECTE'],
          rows: [{ OBJECTE: 'TAB_DEMO' }],
        },
      ],
      query_export: {
        content: 'SELECT 1;',
      },
    },
    error: '',
    executionOrigin: null,
    onRefreshChecks: vi.fn(),
    onProfileChange: vi.fn(),
    onToggleCheck: vi.fn(),
    onSelectAll: vi.fn(),
    onClearAll: vi.fn(),
    onSchemasChange: vi.fn(),
    onTimeFilterChange: vi.fn(),
    onCriticalityOverrideChange: vi.fn(),
    onSchedulerOptionsChange: vi.fn(),
    onResetCriticalityOverrides: vi.fn(),
    onRun: vi.fn(),
    onDownloadQueries: vi.fn(),
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

test('PostCrqAuditView allows switching between general, provider and all report modes', async () => {
  const props = buildProps();
  render(<PostCrqAuditView {...props} />);
  await screen.findByText(/Control de qualitat post-CRQ/i);

  expect(screen.getByDisplayValue('Tots (ZIP)')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Descarregar ZIP' })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Descarregar ZIP' }));

  await waitFor(() => {
    expect(downloadPostCrqReport).toHaveBeenCalledWith(expect.objectContaining({
      profile: 'E13DB',
      variant: 'all',
      summary_version: 'v1',
      provider_code: '',
      report_data: props.result,
    }));
  });

  fireEvent.change(screen.getByDisplayValue('Tots (ZIP)'), { target: { value: 'provider' } });

  expect(screen.getByDisplayValue('LOT_APP')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Descarregar prove/ })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Descarregar prove/ }));

  await waitFor(() => {
    expect(downloadPostCrqReport).toHaveBeenLastCalledWith(expect.objectContaining({
      profile: 'E13DB',
      variant: 'provider',
      summary_version: 'v1',
      provider_code: 'LOT_APP',
      report_data: props.result,
    }));
  });

  fireEvent.change(screen.getByDisplayValue(/prove/), { target: { value: 'general' } });

  expect(screen.getByRole('button', { name: 'Descarregar resum' })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Descarregar resum' }));

  await waitFor(() => {
    expect(downloadPostCrqReport).toHaveBeenLastCalledWith(expect.objectContaining({
      profile: 'E13DB',
      variant: 'general',
      summary_version: 'v1',
      provider_code: '',
      report_data: props.result,
    }));
  });
  expect(screen.queryByRole('button', { name: 'Resum V2' })).not.toBeInTheDocument();
});

test('PostCrqAuditView exposes query export and toggles technical detail', async () => {
  const props = buildProps();

  render(<PostCrqAuditView {...props} />);
  await screen.findByText(/Control de qualitat post-CRQ/i);

  fireEvent.click(screen.getByRole('button', { name: /Descarregar consultes/ }));
  expect(props.onDownloadQueries).toHaveBeenCalledTimes(1);

  expect(screen.queryByText('TAB_DEMO')).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Mostrar detall' }));

  expect(screen.getByRole('button', { name: 'Amagar detall' })).toBeInTheDocument();
  expect(screen.getByText('TAB_DEMO')).toBeInTheDocument();
  expect(screen.getAllByText('CHECK_01').length).toBeGreaterThan(0);

  fireEvent.click(screen.getByRole('button', { name: 'Amagar detall' }));
  expect(screen.queryByText('TAB_DEMO')).not.toBeInTheDocument();
});

test('PostCrqAuditView shows the effective configuration summary and lets you reset criticities', async () => {
  const props = buildProps();
  props.criticalityOverrides = { CHECK_01: 'CRITIC' };
  props.schedulerOptions = {
    max_concurrency: 3,
    max_concurrency_upper_bound: 4,
    max_heavy_concurrency: 1,
    max_medium_concurrency: 1,
    max_light_concurrency: 2,
    max_retries: 1,
    enable_auto_throttle: true,
  };
  props.executionOrigin = {
    mode: 'snapshot',
    label: 'Snapshot del run',
    warning: 'Resultat congelat',
    generatedAt: '2026-04-19 23:45',
  };

  render(<PostCrqAuditView {...props} />);
  await screen.findByText(/Configuració efectiva/i);

  expect(screen.getByText(/Snapshot del run/i)).toBeInTheDocument();
  expect(screen.getByText(/CHECK_01: Cr/i)).toBeInTheDocument();
  expect(screen.getAllByText(/global 3/i).length).toBeGreaterThan(0);

  fireEvent.click(screen.getAllByRole('button', { name: /Restablecer criticidades/i })[0]);
  expect(props.onResetCriticalityOverrides).toHaveBeenCalledTimes(1);
});

test('PostCrqAuditView caches repeated downloads for the same variant in the same session', async () => {
  const props = buildProps();
  render(<PostCrqAuditView {...props} />);
  await screen.findByText(/Control de qualitat post-CRQ/i);

  const downloadButton = screen.getByRole('button', { name: 'Descarregar ZIP' });
  fireEvent.click(downloadButton);

  await waitFor(() => {
    expect(downloadPostCrqReport).toHaveBeenCalledTimes(1);
  });

  fireEvent.click(downloadButton);

  await waitFor(() => {
    expect(downloadPostCrqReport).toHaveBeenCalledTimes(1);
  });
});
