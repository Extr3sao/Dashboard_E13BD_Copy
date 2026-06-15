import { act, renderHook, waitFor } from '@testing-library/react';
import axios from 'axios';

import useGlobalReport from './useGlobalReport.js';

vi.mock('axios', () => ({
  default: {
    post: vi.fn(),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test('useGlobalReport alerts when no audit data is available', () => {
  const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

  const { result } = renderHook(() => useGlobalReport({
    apiBase: '/api',
    activeTab: 'Auditoria BBDD',
    databaseAuditSubtab: 'Anàlisi obsolets',
    selectedProfile: 'E13DB',
    auditData: [],
    postCrqReportData: null,
  }));

  act(() => {
    result.current.handleGenerateReport();
  });

  expect(alertSpy).toHaveBeenCalledWith('Primer executa una auditoria!');
  expect(axios.post).not.toHaveBeenCalled();

  alertSpy.mockRestore();
});

test('useGlobalReport generates the post-crq report and downloads the pdf', async () => {
  const createObjectUrlSpy = vi.fn(() => 'blob:report');
  const originalCreateObjectURL = window.URL.createObjectURL;
  window.URL.createObjectURL = createObjectUrlSpy;

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

  axios.post.mockResolvedValue({ data: new Uint8Array([1, 2, 3]) });

  const { result } = renderHook(() => useGlobalReport({
    apiBase: '/api',
    activeTab: 'Auditoria BBDD',
    databaseAuditSubtab: 'Auditoria de canvis',
    selectedProfile: 'E13DB',
    auditData: [],
    postCrqReportData: {
      audit_type: 'post_crq',
      report_options: { include_summary: true },
      context: { profile: 'E13DB' },
    },
  }));

  act(() => {
    result.current.handleGenerateReport();
  });

  await waitFor(() => {
    expect(axios.post).toHaveBeenCalledWith(
      '/api/report/generate',
      expect.objectContaining({
        profile: 'E13DB',
        format: 'pdf',
        data: expect.objectContaining({
          audit_type: 'post_crq',
          report_options: expect.objectContaining({
            include_summary: true,
            include_annex: true,
          }),
        }),
      }),
      { responseType: 'blob' }
    );
  });

  expect(createObjectUrlSpy).toHaveBeenCalled();
  expect(createdAnchor.download).toBe('report_auditoria_post_crq_E13DB.pdf');
  expect(createdAnchor.click).toHaveBeenCalled();
  await waitFor(() => {
    expect(result.current.loading).toBe(false);
  });

  createElementSpy.mockRestore();
  window.URL.createObjectURL = originalCreateObjectURL;
});

test('useGlobalReport shows backend blob errors when report generation fails', async () => {
  const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
  const errorBlob = new Blob([JSON.stringify({ detail: 'boom report' })], { type: 'application/json' });
  errorBlob.text = () => Promise.resolve(JSON.stringify({ detail: 'boom report' }));

  axios.post.mockRejectedValue({
    response: {
      data: errorBlob,
    },
  });

  const { result } = renderHook(() => useGlobalReport({
    apiBase: '/api',
    activeTab: 'Auditoria BBDD',
    databaseAuditSubtab: 'Anàlisi obsolets',
    selectedProfile: 'E13DB',
    auditData: [{ schema_name: 'SCH1' }],
    postCrqReportData: null,
  }));

  act(() => {
    result.current.handleGenerateReport();
  });

  await waitFor(() => {
    expect(alertSpy).toHaveBeenCalledWith('Error generant report: boom report');
  });
  expect(result.current.loading).toBe(false);

  alertSpy.mockRestore();
});

test('useGlobalReport reuses the same-session cached pdf for identical requests', async () => {
  const createObjectUrlSpy = vi.fn(() => 'blob:report');
  const originalCreateObjectURL = window.URL.createObjectURL;
  window.URL.createObjectURL = createObjectUrlSpy;

  const realCreateElement = document.createElement.bind(document);
  const anchors = [];
  const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tagName) => {
    const element = realCreateElement(tagName);
    if (tagName === 'a') {
      element.click = vi.fn();
      anchors.push(element);
    }
    return element;
  });

  axios.post.mockResolvedValue({ data: new Uint8Array([7, 8, 9]) });

  const { result } = renderHook(() => useGlobalReport({
    apiBase: '/api',
    activeTab: 'Auditoria BBDD',
    databaseAuditSubtab: 'Anàlisi obsolets',
    selectedProfile: 'E13DB',
    auditData: [{ username: 'APP_CORE', obsolescence_score: 42 }],
    postCrqReportData: null,
  }));

  act(() => {
    result.current.handleGenerateReport();
  });

  await waitFor(() => {
    expect(axios.post).toHaveBeenCalledTimes(1);
  });
  await waitFor(() => {
    expect(result.current.loading).toBe(false);
  });

  act(() => {
    result.current.handleGenerateReport();
  });

  expect(axios.post).toHaveBeenCalledTimes(1);
  expect(anchors).toHaveLength(2);
  expect(anchors[1].download).toBe('report_auditoria_detallat_E13DB.pdf');
  expect(anchors[1].click).toHaveBeenCalled();

  createElementSpy.mockRestore();
  window.URL.createObjectURL = originalCreateObjectURL;
});
