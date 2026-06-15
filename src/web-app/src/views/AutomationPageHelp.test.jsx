import { fireEvent, render, screen } from '@testing-library/react';

import AutomationView from './AutomationView.jsx';

vi.mock('../components/AutomationGuide.jsx', () => ({
  default: () => <div>Guia automatitzacions</div>,
}));

vi.mock('../api/automation.js', () => ({
  applyMasterLotsBackfill: vi.fn(() => Promise.resolve({ id: 10, items: [] })),
  createAutomationJob: vi.fn(() => Promise.resolve({ id: 1 })),
  deleteAutomationJob: vi.fn(() => Promise.resolve({ status: 'success' })),
  enqueueRetry: vi.fn(() => Promise.resolve({ status: 'success' })),
  exportAutomationRunLotsCsv: vi.fn(() => Promise.resolve({ data: '', headers: { 'content-type': 'text/csv' } })),
  exportAutomationAnalyticsMonthlyPdf: vi.fn(() => Promise.resolve({ data: '', headers: { 'content-type': 'application/pdf' } })),
  getAutomationAnalyticsOverview: vi.fn(() => Promise.resolve({ runs: 0, total_findings: 0, lots_with_findings: 0, checks_with_errors: 0 })),
  getAutomationMaintenanceSummary: vi.fn(() => Promise.resolve({ auto_purge_enabled: true, history_retention_days: 30, retry_retention_days: 15 })),
  getAutomationRunReportData: vi.fn(() => Promise.resolve({ audit_type: 'post_crq', snapshot_metadata: {} })),
  getAutomationRunReportUrl: vi.fn(() => '/api/automation/runs/1/report'),
  getDeliveryRoutes: vi.fn(() => Promise.resolve({ tic_summary_recipients: [], providers: [] })),
  listAutomationAnalyticsChecks: vi.fn(() => Promise.resolve({ items: [] })),
  listAutomationAnalyticsLots: vi.fn(() => Promise.resolve({ items: [] })),
  listAutomationAnalyticsSchemas: vi.fn(() => Promise.resolve({ items: [] })),
  listAutomationChangeEvents: vi.fn(() => Promise.resolve({ items: [] })),
  listAutomationJobs: vi.fn(() => Promise.resolve({ items: [] })),
  listAutomationRunLotsFiltered: vi.fn(() => Promise.resolve({ items: [] })),
  listAutomationRuns: vi.fn(() => Promise.resolve({ items: [] })),
  listDeliveryTemplates: vi.fn(() => Promise.resolve({ items: [] })),
  listLotRoutes: vi.fn(() => Promise.resolve({ items: [] })),
  listMasterLotBackfillRuns: vi.fn(() => Promise.resolve({ items: [] })),
  listMasterLots: vi.fn(() => Promise.resolve({ items: [] })),
  listRetryQueue: vi.fn(() => Promise.resolve({ items: [] })),
  listSchemaLots: vi.fn(() => Promise.resolve({ items: [] })),
  previewMasterLotsBackfill: vi.fn(() => Promise.resolve({ id: 10, summary: {}, items: [] })),
  purgeAutomationHistory: vi.fn(() => Promise.resolve({ deleted: 0 })),
  purgeAutomationRetryQueue: vi.fn(() => Promise.resolve({ deleted: 0 })),
  runAutomationJobNow: vi.fn(() => Promise.resolve({ status: 'started' })),
  runRetryNow: vi.fn(() => Promise.resolve({ status: 'done' })),
  updateAutomationJob: vi.fn(() => Promise.resolve({ id: 1 })),
  updateDeliveryTemplates: vi.fn(() => Promise.resolve({ items: [] })),
  updateLotRoutes: vi.fn(() => Promise.resolve({ items: [] })),
  updateMasterLots: vi.fn(() => Promise.resolve({ items: [] })),
  updateSchemaLots: vi.fn(() => Promise.resolve({ items: [] })),
}));

vi.mock('../api/postCrqAudit.js', () => ({
  listPostCrqChecks: vi.fn(() => Promise.resolve({ checks: [] })),
}));

beforeEach(() => {
  localStorage.clear();
  window.scrollTo = vi.fn();
  global.IntersectionObserver = class {
    observe() {}
    disconnect() {}
    unobserve() {}
  };
});

test('AutomationView shows contextual help for jobs and lots screens', async () => {
  render(<AutomationView profiles={['E13DB']} />);

  fireEvent.click(await screen.findByRole('button', { name: /Ajuda: Jobs d'automatitzaci/i }));
  expect(await screen.findByRole('dialog', { name: /Jobs d'automatitzaci/i })).toBeInTheDocument();
  expect(screen.getByText(/crear o editar jobs programats/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Tanca ajuda/i }));
  fireEvent.click(screen.getByRole('button', { name: /^Lots i mapatge/i }));
  fireEvent.click(screen.getByRole('button', { name: /Ajuda: Lots i mapatge/i }));

  expect(await screen.findByRole('dialog', { name: /Lots i mapatge/i })).toBeInTheDocument();
  expect(screen.getByText(/Relaciona esquemes amb lots funcionals/i)).toBeInTheDocument();
});
