import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

vi.mock('../api/findings.js', () => ({
  getNeedsAttention: vi.fn(() => Promise.resolve({ items: [{ id: 1, finding_id: 7, priority: 'P1', database_id: 'PROD_DB', finding_summary: 'USERS tablespace usage', finding_delta: 'WORSENING', explanation: 'critical production target' }], summary: { findings: { NEW: 1, WORSENING: 1 }, red_flags: { P1: 1, P2: 0, P3: 0, P4: 0 } } })),
  getFindings: vi.fn(() => Promise.resolve({ items: [{ id: 7, database_id: 'PROD_DB', summary: 'USERS tablespace usage', severity: 'CRITICAL', delta: 'WORSENING', occurrences: 3 }] })),
  getFinding: vi.fn(() => Promise.resolve({ id: 7, database_id: 'PROD_DB', rule_id: 'TABLESPACE_USAGE', summary: 'USERS tablespace usage', severity: 'CRITICAL', status: 'OPEN', delta: 'WORSENING', occurrences: 3, first_seen: 1, last_seen: 2, evidence: '{}', history: [] })),
  applyFindingAction: vi.fn(() => Promise.resolve({ id: 7, status: 'ACKNOWLEDGED', history: [] })),
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
});
