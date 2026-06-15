import { act, renderHook } from '@testing-library/react';

import usePersistedNavigationState from './usePersistedNavigationState.js';

beforeEach(() => {
  localStorage.clear();
});

test('usePersistedNavigationState normalizes legacy storage values on first render', () => {
  localStorage.setItem('activeTab', 'Obsolets');
  localStorage.setItem('databaseAuditSubtab', 'Configuració servidor correu');
  localStorage.setItem('selectedProfile', 'E13DB');

  const { result } = renderHook(() => usePersistedNavigationState());

  expect(result.current.activeTab).toBe('Auditoria BBDD');
  expect(result.current.databaseAuditSubtab).toBe('Anàlisi obsolets');
  expect(result.current.selectedProfile).toBe('E13DB');
});

test('usePersistedNavigationState persists profile and subtab changes', () => {
  const { result } = renderHook(() => usePersistedNavigationState());

  act(() => {
    result.current.setSelectedProfile('E13QA');
    result.current.setDatabaseAuditSubtab('Guia i Ajuda');
    result.current.setActiveTab('Auditoria BBDD');
  });

  expect(localStorage.getItem('selectedProfile')).toBe('E13QA');
  expect(localStorage.getItem('databaseAuditSubtab')).toBe('Guia i Ajuda');
  expect(localStorage.getItem('activeTab')).toBe('Auditoria BBDD');
});
