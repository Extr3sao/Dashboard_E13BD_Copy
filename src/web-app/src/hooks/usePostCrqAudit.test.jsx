import { act, renderHook, waitFor } from '@testing-library/react';

import usePostCrqAudit from './usePostCrqAudit.js';
import { listPostCrqChecks, runPostCrqAudit } from '../api/postCrqAudit.js';

vi.mock('../api/postCrqAudit.js', () => ({
  listPostCrqChecks: vi.fn(),
  runPostCrqAudit: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

test('usePostCrqAudit loads checks on entry and restores persisted options', async () => {
  localStorage.setItem('postCrqSchedulerOptions', JSON.stringify({ max_concurrency: 3, max_retries: 0 }));
  localStorage.setItem('postCrqCriticalityOverrides', JSON.stringify({ CHECK_2: 'BAIX' }));
  listPostCrqChecks.mockResolvedValue({
    checks: [
      { check_id: 'CHECK_1' },
      { check_id: 'CHECK_2' },
    ],
  });

  const { result } = renderHook(() => usePostCrqAudit({
    activeTab: 'Auditoria BBDD',
    databaseAuditSubtab: 'Auditoria de canvis',
    selectedProfile: 'E13DB',
    defaultTimeFilter: { mode: 'relative', days_back: 7 },
    defaultSchedulerOptions: { max_concurrency: 2, max_retries: 1 },
    defaultCriticalityOverrides: { CHECK_1: 'MITJA' },
  }));

  await waitFor(() => {
    expect(result.current.postCrqChecks).toHaveLength(2);
  });

  expect(listPostCrqChecks).toHaveBeenCalled();
  expect(result.current.postCrqSchedulerOptions).toEqual({ max_concurrency: 3, max_retries: 0 });
  expect(result.current.postCrqCriticalityOverrides).toEqual({ CHECK_1: 'MITJA', CHECK_2: 'BAIX' });
});

test('usePostCrqAudit runs the audit with normalized payload and stores the result', async () => {
  listPostCrqChecks.mockResolvedValue({ checks: [{ check_id: 'CHECK_1' }] });
  runPostCrqAudit.mockResolvedValue({
    audit_type: 'post_crq',
    query_export: { content: 'select 1;', filename: 'queries.txt' },
  });

  const { result } = renderHook(() => usePostCrqAudit({
    activeTab: 'Auditoria BBDD',
    databaseAuditSubtab: 'Auditoria de canvis',
    selectedProfile: 'E13DB',
    defaultTimeFilter: { mode: 'relative', days_back: 7 },
    defaultSchedulerOptions: { max_concurrency: 2, max_retries: 1 },
    defaultCriticalityOverrides: {},
  }));

  await waitFor(() => {
    expect(result.current.postCrqChecks).toHaveLength(1);
  });

  act(() => {
    result.current.setSelectedChecks(['CHECK_1']);
    result.current.setPostCrqSchemas(' SCH1 , SCH2 ');
    result.current.setPostCrqTimeFilter({ mode: 'relative', days_back: 14 });
    result.current.setPostCrqSchedulerOptions({ max_concurrency: 4, max_retries: 0 });
    result.current.setPostCrqCriticalityOverrides({ CHECK_1: 'CRITIC' });
  });

  act(() => {
    result.current.handleRunPostCrqAudit();
  });

  await waitFor(() => {
    expect(runPostCrqAudit).toHaveBeenCalledWith({
      profile: 'E13DB',
      schemas: ['SCH1', 'SCH2'],
      time_filter: { mode: 'relative', days_back: 14 },
      selected_checks: ['CHECK_1'],
      criticality_overrides: { CHECK_1: 'CRITIC' },
      scheduler_options: expect.objectContaining({ max_concurrency: 4, max_retries: 0 }),
    });
  });

  await waitFor(() => {
    expect(result.current.postCrqReportData).toEqual({
      audit_type: 'post_crq',
      query_export: { content: 'select 1;', filename: 'queries.txt' },
    });
  });
  expect(result.current.isPostCrqRunning).toBe(false);
});

test('usePostCrqAudit migrates away legacy hidden criticality overrides and can reset them', async () => {
  localStorage.setItem('postCrqCriticalityOverrides', JSON.stringify({ CHECK_03: 'CRITIC', CHECK_04: 'CRITIC' }));
  listPostCrqChecks.mockResolvedValue({ checks: [{ check_id: 'CHECK_03' }, { check_id: 'CHECK_04' }] });

  const { result } = renderHook(() => usePostCrqAudit({
    activeTab: 'Auditoria BBDD',
    databaseAuditSubtab: 'Auditoria de canvis',
    selectedProfile: 'E13DB',
    defaultTimeFilter: { mode: 'preset', preset: 'weekly' },
    defaultSchedulerOptions: { max_concurrency: 2 },
    defaultCriticalityOverrides: {},
  }));

  await waitFor(() => {
    expect(result.current.postCrqChecks).toHaveLength(2);
  });

  expect(result.current.postCrqCriticalityOverrides).toEqual({});
  expect(localStorage.getItem('postCrqCriticalityOverridesVersion')).toBe('2026-04-20');

  act(() => {
    result.current.setPostCrqCriticalityOverrides({ CHECK_03: 'MITJA' });
  });
  expect(result.current.postCrqCriticalityOverrides).toEqual({ CHECK_03: 'MITJA' });

  act(() => {
    result.current.resetPostCrqCriticalityOverrides();
  });
  expect(result.current.postCrqCriticalityOverrides).toEqual({});
});

test('usePostCrqAudit exports queries when the run has query content', async () => {
  listPostCrqChecks.mockResolvedValue({ checks: [{ check_id: 'CHECK_1' }] });
  runPostCrqAudit.mockResolvedValue({
    audit_type: 'post_crq',
    query_export: { content: 'select * from dual;', filename: 'queries.txt' },
  });

  const createObjectUrlSpy = vi.fn(() => 'blob:queries');
  const revokeObjectUrlSpy = vi.fn();
  const originalCreateObjectURL = window.URL.createObjectURL;
  const originalRevokeObjectURL = window.URL.revokeObjectURL;
  window.URL.createObjectURL = createObjectUrlSpy;
  window.URL.revokeObjectURL = revokeObjectUrlSpy;

  const realCreateElement = document.createElement.bind(document);
  let createdAnchor = null;
  const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tagName) => {
    const element = realCreateElement(tagName);
    if (tagName === 'a') {
      createdAnchor = element;
      element.click = vi.fn();
    }
    return element;
  });

  const { result } = renderHook(() => usePostCrqAudit({
    activeTab: 'Auditoria BBDD',
    databaseAuditSubtab: 'Auditoria de canvis',
    selectedProfile: 'E13DB',
    defaultTimeFilter: { mode: 'relative', days_back: 7 },
    defaultSchedulerOptions: { notify_tic: true },
    defaultCriticalityOverrides: {},
  }));

  await waitFor(() => {
    expect(result.current.postCrqChecks).toHaveLength(1);
  });

  act(() => {
    result.current.setSelectedChecks(['CHECK_1']);
  });

  act(() => {
    result.current.handleRunPostCrqAudit();
  });

  await waitFor(() => {
    expect(result.current.postCrqReportData?.query_export?.filename).toBe('queries.txt');
  });

  act(() => {
    result.current.handleDownloadPostCrqQueries();
  });

  expect(createObjectUrlSpy).toHaveBeenCalled();
  expect(createdAnchor.download).toBe('queries.txt');
  expect(createdAnchor.click).toHaveBeenCalled();
  expect(revokeObjectUrlSpy).toHaveBeenCalledWith('blob:queries');

  createElementSpy.mockRestore();
  window.URL.createObjectURL = originalCreateObjectURL;
  window.URL.revokeObjectURL = originalRevokeObjectURL;
});

test('usePostCrqAudit reuses the cached query blob on repeated download', async () => {
  listPostCrqChecks.mockResolvedValue({ checks: [{ check_id: 'CHECK_1' }] });
  runPostCrqAudit.mockResolvedValue({
    audit_type: 'post_crq',
    query_export: { content: 'select * from dual;', filename: 'queries.txt' },
  });

  const createObjectUrlSpy = vi.fn(() => 'blob:queries');
  const revokeObjectUrlSpy = vi.fn();
  const originalCreateObjectURL = window.URL.createObjectURL;
  const originalRevokeObjectURL = window.URL.revokeObjectURL;
  window.URL.createObjectURL = createObjectUrlSpy;
  window.URL.revokeObjectURL = revokeObjectUrlSpy;

  const BlobSpy = vi.spyOn(globalThis, 'Blob');
  const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

  const { result } = renderHook(() => usePostCrqAudit({
    activeTab: 'Auditoria BBDD',
    databaseAuditSubtab: 'Auditoria de canvis',
    selectedProfile: 'E13DB',
    defaultTimeFilter: { mode: 'relative', days_back: 7 },
    defaultSchedulerOptions: { notify_tic: true },
    defaultCriticalityOverrides: {},
  }));

  await waitFor(() => {
    expect(result.current.postCrqChecks).toHaveLength(1);
  });

  act(() => {
    result.current.setSelectedChecks(['CHECK_1']);
  });

  act(() => {
    result.current.handleRunPostCrqAudit();
  });

  await waitFor(() => {
    expect(result.current.postCrqReportData?.query_export?.filename).toBe('queries.txt');
  });

  act(() => {
    result.current.handleDownloadPostCrqQueries();
  });
  act(() => {
    result.current.handleDownloadPostCrqQueries();
  });

  expect(BlobSpy).toHaveBeenCalledTimes(1);
  expect(createObjectUrlSpy).toHaveBeenCalledTimes(2);
  expect(revokeObjectUrlSpy).toHaveBeenCalledTimes(2);

  BlobSpy.mockRestore();
  alertSpy.mockRestore();
  window.URL.createObjectURL = originalCreateObjectURL;
  window.URL.revokeObjectURL = originalRevokeObjectURL;
});
