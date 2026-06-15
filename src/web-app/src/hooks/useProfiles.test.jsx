import { renderHook, waitFor } from '@testing-library/react';
import axios from 'axios';

import useProfiles from './useProfiles.js';

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test('useProfiles loads profiles and applies the default profile', async () => {
  const onDefaultProfile = vi.fn();
  axios.get.mockResolvedValue({ data: { profiles: ['E13DB', 'E13QA'], default: 'E13QA' } });

  const { result } = renderHook(() => useProfiles({ apiBase: '/api', onDefaultProfile }));

  await waitFor(() => {
    expect(result.current.profiles).toEqual(['E13DB', 'E13QA']);
  });
  expect(axios.get).toHaveBeenCalledWith('/api/profiles');
  expect(onDefaultProfile).toHaveBeenCalledWith('E13QA');
});

test('useProfiles logs and preserves empty profiles on request failure', async () => {
  const onDefaultProfile = vi.fn();
  const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  axios.get.mockRejectedValue(new Error('network down'));

  const { result } = renderHook(() => useProfiles({ apiBase: '/api', onDefaultProfile }));

  await waitFor(() => {
    expect(errorSpy).toHaveBeenCalled();
  });
  expect(result.current.profiles).toEqual([]);
  expect(onDefaultProfile).not.toHaveBeenCalled();

  errorSpy.mockRestore();
});
