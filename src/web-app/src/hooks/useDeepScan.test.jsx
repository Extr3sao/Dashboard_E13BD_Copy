import { act, renderHook, waitFor } from '@testing-library/react';
import axios from 'axios';

import useDeepScan from './useDeepScan.js';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

test('useDeepScan runs the audit with cleaned input and resets result state', async () => {
  axios.get.mockResolvedValue({ data: [{ schema_name: 'APP_CORE' }, { schema_name: 'APP_AUX' }] });

  const { result } = renderHook(() => useDeepScan({
    apiBase: '/api',
    selectedProfile: 'E13DB',
    defaultScoringConfig: { ownerWeight: 20 },
  }));

  act(() => {
    result.current.setSchemaToAudit(" 'APP_CORE' ");
    result.current.setSelectedAuditIndex(3);
  });

  act(() => {
    result.current.runDeepAudit();
  });

  expect(result.current.isAuditing).toBe(true);
  expect(result.current.selectedAuditIndex).toBe(0);
  expect(result.current.auditData).toEqual([]);

  await waitFor(() => {
    expect(axios.get).toHaveBeenCalledWith('/api/audit/deep-scan/APP_CORE?profile=E13DB');
  });

  await waitFor(() => {
    expect(result.current.auditData).toEqual([{ schema_name: 'APP_CORE' }, { schema_name: 'APP_AUX' }]);
  });
  expect(result.current.selectedAuditIndex).toBe(0);
  expect(result.current.isAuditing).toBe(false);
});

test('useDeepScan tests the connection and clears transient status after timeout', async () => {
  vi.useFakeTimers();
  axios.post.mockResolvedValue({ data: { status: 'ok', message: 'Connexió correcta' } });

  const { result } = renderHook(() => useDeepScan({
    apiBase: '/api',
    selectedProfile: 'E13DB',
    defaultScoringConfig: { ownerWeight: 20 },
  }));

  act(() => {
    result.current.handleTestDeepConnection();
  });

  expect(result.current.testStatusDeep).toEqual({ status: 'loading', msg: 'Provant...' });
  expect(axios.post).toHaveBeenCalledWith('/api/db/test', { profile: 'E13DB' });

  await act(async () => {
    await Promise.resolve();
  });

  expect(result.current.testStatusDeep).toEqual({ status: 'ok', msg: 'Connexió correcta' });

  act(() => {
    vi.advanceTimersByTime(5000);
  });

  expect(result.current.testStatusDeep).toBe(null);
});

test('useDeepScan alerts when schema or profile are missing', () => {
  const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

  const { result } = renderHook(() => useDeepScan({
    apiBase: '/api',
    selectedProfile: '',
    defaultScoringConfig: { ownerWeight: 20 },
  }));

  act(() => {
    result.current.runDeepAudit();
  });
  expect(alertSpy).toHaveBeenCalledWith('Escriu un esquema o llista!');

  act(() => {
    result.current.handleTestDeepConnection();
  });
  expect(alertSpy).toHaveBeenCalledWith('Selecciona un perfil!');

  alertSpy.mockRestore();
});
