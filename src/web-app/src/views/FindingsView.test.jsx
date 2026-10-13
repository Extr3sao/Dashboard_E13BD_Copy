import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { getInvestigations } from '../api/investigations.js';
import { getFinding } from '../api/findings.js';

vi.mock('../api/findings.js', () => ({
  getNeedsAttention: vi.fn(() => Promise.resolve({ items: [{ id: 1, finding_id: 7, priority: 'P1', database_id: 'PROD_DB', finding_summary: 'USERS tablespace usage', finding_delta: 'WORSENING', explanation: 'critical production target' }], summary: { findings: { NEW: 1, WORSENING: 1 }, red_flags: { P1: 1, P2: 0, P3: 0, P4: 0 } } })),
  getFindings: vi.fn(() => Promise.resolve({ items: [{ id: 7, database_id: 'PROD_DB', summary: 'USERS tablespace usage', severity: 'CRITICAL', delta: 'WORSENING', occurrences: 3 }] })),
  getFinding: vi.fn(() => Promise.resolve({ id: 7, database_id: 'PROD_DB', rule_id: 'TABLESPACE_USAGE', summary: 'USERS tablespace usage', severity: 'CRITICAL', status: 'OPEN', delta: 'WORSENING', occurrences: 3, first_seen: 1, last_seen: 2, evidence: '{}', history: [] })),
  applyFindingAction: vi.fn(() => Promise.resolve({ id: 7, status: 'ACKNOWLEDGED', history: [] })),
}));
vi.mock('../api/investigations.js', () => ({
  getInvestigations: vi.fn(() => Promise.resolve({ items: [] })),
  openInvestigation: vi.fn(() => Promise.resolve({ id: 3 })),
}));

import FindingsView from './FindingsView.jsx';

describe('FindingsView', () => {
  test('shows prioritised operational attention and finding detail', async () => {
    render(<FindingsView />);
    expect(await screen.findByText('Needs Attention')).toBeInTheDocument();
    expect(screen.getByText('RED FLAGS P1')).toBeInTheDocument();
    fireEvent.click(screen.getAllByText('USERS tablespace usage')[0]);
    expect(await screen.findByRole('dialog', { name: 'Finding detail' })).toBeInTheDocument();
    expect(screen.getByText('Operator action')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/Current \/ previous value/i)).toBeInTheDocument());
  });

  test('database Findings view links investigation and recent explained correlation', async () => {
    vi.mocked(getInvestigations).mockResolvedValueOnce({ items: [{ id: 3, database_id: 'PROD_DB', status: 'OPEN', summary: 'Existing DWH investigation', primary_finding: { summary: 'USERS tablespace usage' }, top_hypothesis: 'Capacity may be relevant', recent_correlation: { strength: 'RELATED', reasons: ['same tablespace'] } }] });
    const opened = vi.fn();
    window.addEventListener('e13db-open-investigation', opened);
    render(<FindingsView database="PROD_DB" />);
    expect(await screen.findByText('Active Investigations · PROD_DB')).toBeInTheDocument();
    expect(screen.getByText(/Recent correlation: RELATED · same tablespace/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: /USERS tablespace usage/ })[0]);
    expect(opened).toHaveBeenCalled();
    window.removeEventListener('e13db-open-investigation', opened);
  });

  test('diagnostic navigation opens the requested Finding evidence', async () => {
    localStorage.setItem('e13db:selected-finding-id','7');
    render(<FindingsView database="PROD_DB" />);
    expect(await screen.findByRole('dialog',{name:'Finding detail'})).toBeInTheDocument();
    expect(getFinding).toHaveBeenCalledWith(7);
    expect(localStorage.getItem('e13db:selected-finding-id')).toBeNull();
  });
});
