import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import axios from 'axios';
import OperationsView from './OperationsView.jsx';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
const summary = {
  status: 'DEGRADED', reason: 'Email delivery unavailable; audits and findings continue.', updated_at: 1790812800,
  components: { 'Notification Engine': { status: 'DEGRADED', reason: 'SMTP unavailable.', last_failure: 1790812800, recommended_action: 'Verify SMTP connectivity.' } },
  scheduler: { enabled: true, owner: 'owner-1', heartbeat: 1790812800, running_jobs: 2, queued_jobs: 1, failed_jobs: 3, missed_policy: 'run_once' },
  storage: [{ name: 'internal', database_size: 1048576, wal_size: 0, available_bytes: 1024**3, disk_status: 'HEALTHY' }],
  integrity: { status: 'PASS', checked_at: 1790812800 }, backup: { status: 'SUCCESS', size: 1048576, integrity: 'PASS', created_at: 1790812800 },
  configuration: { status: 'VALID', diagnostics: [] }, retention: { audit_history: 365 },
};
beforeEach(() => {
  vi.clearAllMocks();
  axios.get.mockImplementation(async (url) => ({ data: url.endsWith('timeline') ? { items: [{ id: 1, component: 'Notification Engine', status: 'DEGRADED', reason: 'Email failed', created_at: 1790812800 }] } : url.endsWith('preview') ? { eligible_records: { audit_runs: 22 }, reclaim_note: 'Pages reused' } : summary }));
  axios.post.mockResolvedValue({ data: { status: 'SUCCESS', backup_id: 'backup-1' } });
});

test('operator diagnoses delivery failure without raw logs or JSON', async () => {
  render(<OperationsView />);
  expect(await screen.findByText('Email delivery unavailable; audits and findings continue.')).toBeInTheDocument();
  expect(screen.getByText('Verify SMTP connectivity.')).toBeInTheDocument();
  expect(screen.getByText('SMTP unavailable.')).toBeInTheDocument();
  expect(screen.getByText('Owner: owner-1')).toBeInTheDocument();
  expect(screen.getByText('Email failed')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Create Backup' })).toBeEnabled();
});

test('backup action confirms verification and refreshes health', async () => {
  render(<OperationsView />);
  fireEvent.click(await screen.findByRole('button', { name: 'Create Backup' }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/api/operations/backups'));
  expect(await screen.findByRole('status')).toHaveTextContent('Backup verified: backup-1');
});

test('retention preview cannot delete records', async () => {
  render(<OperationsView />);
  fireEvent.click(await screen.findByRole('button', { name: 'Preview retention purge' }));
  expect(await screen.findByText('audit runs: 22 eligible')).toBeInTheDocument();
  expect(axios.post).not.toHaveBeenCalled();
  expect(screen.getByRole('status')).toHaveTextContent('No records deleted');
});

test('failed backup gives useful operator action', async () => {
  axios.post.mockRejectedValue({ response: { data: { detail: 'Verify disk space and directory permissions.' } } });
  render(<OperationsView />);
  fireEvent.click(await screen.findByRole('button', { name: 'Create Backup' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Verify disk space and directory permissions.');
});

test('unavailable service has visible initial diagnostics', async () => {
  axios.get.mockRejectedValue(new Error('offline'));
  render(<OperationsView />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Verify service readiness and your session.');
});
