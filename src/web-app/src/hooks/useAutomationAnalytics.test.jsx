import { act, renderHook, waitFor } from '@testing-library/react';

import { useAutomationAnalytics } from './useAutomationAnalytics.js';
import {
  exportAutomationAnalyticsMonthlyPdf,
  getAutomationAnalyticsOverview,
  listAutomationAnalyticsChecks,
  listAutomationAnalyticsLots,
  listAutomationAnalyticsSchemas,
} from '../api/automation.js';
import { downloadBlob } from '../utils/automationViewUtils.js';

vi.mock('../api/automation.js', () => ({
  exportAutomationAnalyticsMonthlyPdf: vi.fn(),
  getAutomationAnalyticsOverview: vi.fn(),
  listAutomationAnalyticsChecks: vi.fn(),
  listAutomationAnalyticsLots: vi.fn(),
  listAutomationAnalyticsSchemas: vi.fn(),
}));

vi.mock('../utils/automationViewUtils.js', () => ({
  currentMonthValue: () => '2026-03',
  downloadBlob: vi.fn(),
  resolveRequestErrorMessage: vi.fn(async (_error, fallback) => fallback),
}));

beforeEach(() => {
  vi.clearAllMocks();
  getAutomationAnalyticsOverview.mockResolvedValue({ total_runs: 3 });
  listAutomationAnalyticsLots.mockResolvedValue({ items: [{ lot: 'AM10' }] });
  listAutomationAnalyticsSchemas.mockResolvedValue({ items: [{ schema_name: 'APP_CORE' }] });
  listAutomationAnalyticsChecks.mockResolvedValue({ items: [{ check_id: 'CHECK_01' }] });
});

test('useAutomationAnalytics caches repeated monthly pdf exports in the same session', async () => {
  const setError = vi.fn();
  exportAutomationAnalyticsMonthlyPdf.mockResolvedValue({
    data: new Uint8Array([1, 2, 3]),
    headers: { 'content-type': 'application/pdf' },
  });

  const { result } = renderHook(() => useAutomationAnalytics(setError));

  await waitFor(() => {
    expect(getAutomationAnalyticsOverview).toHaveBeenCalledWith('2026-03');
  });

  await act(async () => {
    await result.current.handleExportAnalyticsPdf();
  });

  expect(exportAutomationAnalyticsMonthlyPdf).toHaveBeenCalledTimes(1);
  expect(downloadBlob).toHaveBeenCalledTimes(1);

  await act(async () => {
    await result.current.handleExportAnalyticsPdf();
  });

  expect(exportAutomationAnalyticsMonthlyPdf).toHaveBeenCalledTimes(1);
  expect(downloadBlob).toHaveBeenCalledTimes(2);
  expect(setError).not.toHaveBeenCalled();
});
