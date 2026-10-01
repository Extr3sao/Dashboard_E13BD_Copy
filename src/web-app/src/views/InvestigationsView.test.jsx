import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import { beforeEach, expect, test, vi } from 'vitest';
import InvestigationsView from './InvestigationsView.jsx';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const item = {
  id: 3, database_id: 'DWH-TEST', status: 'OPEN', source: 'automatic', opened_at: 1000,
  summary: 'SQL elapsed time increased', primary_finding_id: 9,
  primary_finding: { id: 9, database_id: 'DWH-TEST', rule_id: 'SQL_ELAPSED', summary: 'SQL execution duration increased', severity: 'CRITICAL', delta: 'WORSENING' },
  top_hypothesis: 'Execution plan change may be contributing', next_recommended_check: 'Compare current and previous execution plans.',
};
const detail = {
  ...item, facts: [{ id: 21, category: 'PERFORMANCE', observed_at: 1000, summary: 'SQL execution duration increased', rule_id: 'SQL_ELAPSED', owner: 'APP', object_name: 'ORDERS', metric_name: 'elapsed_seconds', value_json: '11.4', unit: 's' }],
  timeline: [{ type: 'FACT', at: 1000, summary: 'SQL execution duration increased', category: 'PERFORMANCE' }],
  correlations: [{ id: 1, category: 'EXECUTION_PLAN', strength: 'RELATED', occurred_at: 1001, reasons: ['same database', 'documented rule relationship'], finding: { database_id: 'DWH-TEST', rule_id: 'SQL_PLAN', summary: 'Execution plan changed' } }],
  hypotheses: [{ id: 7, hypothesis_type: 'PLAN_CHANGE_MAY_CONTRIBUTE', title: 'Execution plan change may be contributing', description: 'Plan and performance evidence overlap. This does not establish causation.', status: 'SUPPORTED', supporting_evidence: [21], contradicting_evidence: [], recommended_checks: ['Compare plans'] }],
  recommended_checks: [{ id: 4, description: 'Compare current and previous execution plans.', status: 'PENDING' }],
  recurrence: [], confirmed_cause: null,
};

beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear();
  axios.get.mockImplementation(async (url) => ({ data: url.endsWith('/capabilities') ? { awr: { status: 'SKIPPED' }, ash: { status: 'SKIPPED' } } : url === '/api/investigations' ? { items: [item] } : detail }));
  axios.post.mockResolvedValue({ data: detail });
});

test('DBA sees structured facts, justified correlation, hypothesis and safe next check', async () => {
  render(<InvestigationsView />);
  expect(await screen.findByText('SQL execution duration increased')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /DWH-TEST/ }));
  expect(await screen.findByText('FACT · PERFORMANCE')).toBeInTheDocument();
  expect(screen.getByText(/CORRELATION — why:/)).toBeInTheDocument();
  expect(screen.getByText('Why this hypothesis?')).toBeInTheDocument();
  fireEvent.click(screen.getByText('Why this hypothesis?'));
  expect(await screen.findByText(/does not establish causation/i)).toBeInTheDocument();
  expect(screen.getByText('Compare current and previous execution plans.')).toBeInTheDocument();
  expect(screen.queryByText(/Evidence observation 21/)).not.toBeInTheDocument();
});

test('operator can confirm cause, record resolution and complete a check', async () => {
  render(<InvestigationsView />);
  fireEvent.click(await screen.findByRole('button', { name: /DWH-TEST/ }));
  expect(await screen.findByText('FACT · PERFORMANCE')).toBeInTheDocument();
  fireEvent.change(screen.getByPlaceholderText('Describe confirmed cause and evidence basis'), { target: { value: 'Blocking transaction confirmed by DBA' } });
  fireEvent.click(screen.getByRole('button', { name: 'Record confirmed cause' }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/api/investigations/3/cause', expect.objectContaining({ description: 'Blocking transaction confirmed by DBA' })));
  fireEvent.click(screen.getByRole('button', { name: 'Completed' }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/api/investigations/3/checks/4', expect.objectContaining({ status: 'COMPLETED' })));
  fireEvent.change(screen.getByPlaceholderText('Resolution summary'), { target: { value: 'Service returned to baseline' } });
  fireEvent.click(screen.getByRole('button', { name: 'Record resolution' }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/api/investigations/3/resolution', expect.objectContaining({ resolution: 'Service returned to baseline' })));
});

test('active case navigation persists its ID and gives session diagnostics on API failure', async () => {
  render(<InvestigationsView />);
  fireEvent.click(await screen.findByRole('button', { name: /DWH-TEST/ }));
  await waitFor(() => expect(localStorage.getItem('e13db:selected-investigation-id')).toBe('3'));
  axios.get.mockRejectedValue(new Error('offline'));
  render(<InvestigationsView />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Investigations are unavailable. Verify your session and service readiness.');
});
