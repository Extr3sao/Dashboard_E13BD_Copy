import { act, renderHook } from '@testing-library/react';

import { useAutomationHistoryRetries } from './useAutomationHistoryRetries.js';
import { exportAutomationRunLotsCsv } from '../api/automation.js';
import { downloadBlob } from '../utils/automationViewUtils.js';

vi.mock('../api/automation.js', () => ({
  enqueueRetry: vi.fn(),
  exportAutomationRunLotsCsv: vi.fn(),
  getAutomationMaintenanceSummary: vi.fn(),
  listAutomationRunLotsFiltered: vi.fn(),
  purgeAutomationHistory: vi.fn(),
  purgeAutomationRetryQueue: vi.fn(),
  runRetryNow: vi.fn(),
}));

vi.mock('../utils/automationViewUtils.js', () => ({
  downloadBlob: vi.fn(),
  resolveRequestErrorMessage: vi.fn(async (_error, fallback) => fallback),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test('useAutomationHistoryRetries caches repeated run csv exports for the same filter set', async () => {
  exportAutomationRunLotsCsv.mockResolvedValue({
    data: 'lot,status\nLOT_APP,OK\n',
    headers: { 'content-type': 'text/csv;charset=utf-8' },
  });

  const { result } = renderHook(() => useAutomationHistoryRetries({
    setError: vi.fn(),
    setMessage: vi.fn(),
  }));

  await act(async () => {
    await result.current.handleExportRunCsv(77);
  });

  expect(exportAutomationRunLotsCsv).toHaveBeenCalledTimes(1);
  expect(downloadBlob).toHaveBeenCalledTimes(1);

  await act(async () => {
    await result.current.handleExportRunCsv(77);
  });

  expect(exportAutomationRunLotsCsv).toHaveBeenCalledTimes(1);
  expect(downloadBlob).toHaveBeenCalledTimes(2);
});
