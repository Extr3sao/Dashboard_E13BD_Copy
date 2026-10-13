import React from 'react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import axios from 'axios';
import OracleDiagnosticsView from './OracleDiagnosticsView.jsx';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));

const blocker = {
  audit_run_id: 'diag-1', database_id: 'DWH', category: 'BLOCKING', identity_key: 'inst=1:con=5:sid=128:serial=900',
  observed_at: 1800000000, inst_id: 1, con_id: 5,
  metrics: { affected_sessions: 3, chain_depth: 2, observed_duration_seconds: 120, sample_count: 2 },
  evidence: { root_blocker: 'inst=1:con=5:sid=128:serial=900', root_blocker_name: 'APP', observation_note: 'Observed across scheduled snapshots; sample interval is not proof of continuous blocking.', chain: [{ blocking_instance: 1, blocking_session: 128, blocked_instance: 2, blocked_session: 244, wait_class: 'Application', event: 'enq: TX', wait_seconds: 60 }] },
};
const capacity = {
  audit_run_id: 'diag-1', database_id: 'DWH', category: 'CAPACITY', identity_key: 'capacity:con=5:tablespace=APP_DATA',
  observed_at: 1800000001, con_id: 5, owner: 'TABLESPACE', object_name: 'APP_DATA',
  metrics: { capacity_known: true, allocated_bytes: 1000, used_bytes: 950, free_bytes: 50, max_bytes: 4000, used_percent: 95, max_capacity_percent: 23.75, autoextend_headroom_bytes: 3000, effective_free_capacity_bytes: 3050, quota_used_bytes: 50, quota_limit_bytes: 100, quota_used_percent: 50, quota_unlimited: false },
  evidence: { tablespace: 'APP_DATA', contents: 'PERMANENT', warning_percent: 80, critical_percent: 95, physical_capacity_status: 'UNKNOWN_NOT_EXPOSED_BY_CURRENT_ORACLE_DICTIONARY_PROBES' },
};
const detail = {
  audit_run_id: 'diag-1', state: 'SUCCESS', audit_state: 'SUCCESS', coverage_state: 'DEGRADED', reconciliation_state: 'RECONCILED', trigger_type: 'SCHEDULED',
  summary: { checks_total: 3, checks_fail: 1, checks_error: 1, checks_skipped: 0, query_count: 3, queries_executed: 3, queries_failed: 1, queries_skipped: 0, query_budget: 8, query_metrics: [{ rule_id: 'ORACLE_SESSIONS', status: 'AVAILABLE' }, { rule_id: 'ORACLE_BLOCKING', status: 'AVAILABLE' }, { rule_id: 'ORACLE_CAPACITY', status: 'ERROR' }] },
  runtime_identity: { git_sha: 'fixture' }, execution_options: { tablespace_warning_percent: 80, tablespace_critical_percent: 95 },
  rule_results: [
    { rule_id: 'ORACLE_BLOCKING', status: 'FAIL', severity: 'MEDIUM', summary: 'Root blocker affects 3 sessions', coverage_meaning: 'evaluated' },
    { rule_id: 'ORACLE_CAPACITY', status: 'ERROR', severity: 'MEDIUM', summary: 'ORACLE_QUERY_TIMEOUT', error: 'ORACLE_QUERY_TIMEOUT', coverage_meaning: 'evaluation_error' },
  ],
  diagnostic_errors: [{ rule_id: 'ORACLE_CAPACITY', error_class: 'ORACLE_QUERY_TIMEOUT' }],
  capability_snapshot: { snapshot_id: 'cap-1', snapshot_hash: 'cap-hash', snapshot: { capabilities: { SESSION_VISIBILITY: 'AVAILABLE', LOCK_VISIBILITY: 'AVAILABLE', STORAGE_VISIBILITY: 'AVAILABLE', AWR_ALLOWED: 'NOT_LICENSED', ASH_ALLOWED: 'NOT_LICENSED' }, reasons: { SESSION_VISIBILITY: 'Read-only metadata probe succeeded.' }, connection_class: 'AVAILABLE', rac_instance_count: 2, cdb_mode: 'CDB', current_container_id: 5, license_gates: { disclosure: 'AWR/ASH data views are never queried here. AVAILABLE requires explicit license acknowledgement and privilege attestation.' } } },
};

function history(items = [blocker, capacity], latestAudit = detail, offset = 0, total = items.length) {
  return { items, latest_audit: latestAudit, offset, total, limit: 50 };
}

beforeEach(() => {
  localStorage.clear();
  axios.get.mockImplementation(async (url, config = {}) => {
    if (url.includes('/history')) return { data: history([blocker, capacity], detail, config.params?.offset || 0, 2) };
    if (url === '/api/findings') return { data: { items: [{ id: 77, database_id: 'DWH', rule_id: 'ORACLE_BLOCKING', object_name: blocker.identity_key, severity: 'CRITICAL', delta: 'NEW', status: 'OPEN', evidence: JSON.stringify({ sql_id: 'SQLA' }) }] } };
    throw new Error(`Unexpected GET ${url}`);
  });
  axios.post.mockResolvedValue({ data: { audit_run_id: 'diag-manual-2', audit_state: 'SUCCESS', coverage_state: 'FULL', reconciliation_state: 'RECONCILED', summary: { checks_total: 1, checks_pass: 1, query_count: 1, queries_executed: 1, queries_failed: 0, queries_skipped: 0, query_budget: 8 }, rule_results: [], diagnostic_observations: [blocker], finding_envelopes: [] } });
});

afterEach(() => { cleanup(); vi.clearAllMocks(); vi.useRealTimers(); });

test('la vista està en català, explica cobertura parcial i obre incidències traçables', async () => {
  const dispatch = vi.spyOn(window, 'dispatchEvent');
  render(<OracleDiagnosticsView profiles={['DWH']} selectedProfile="DWH"/>);
  expect(await screen.findByText('Resum executiu')).toBeInTheDocument();
  expect(screen.getByText(/3 executades · 2 correctes · 1 fallides/)).toBeInTheDocument();
  expect(screen.getByText(/Cobertura parcial:/)).toBeInTheDocument();
  expect(screen.getByText(/SID 128/)).toBeInTheDocument();
  expect(screen.getAllByText(/enq: TX/).length).toBeGreaterThan(0);
  expect(screen.getByText(/Instàncies RAC: 2/)).toBeInTheDocument();
  expect(screen.getAllByText(/Sense llicència declarada/).length).toBeGreaterThan(0);
  expect(screen.getByText(/Quota de l’usuari Oracle connectat/)).toBeInTheDocument();
  expect(screen.getByText(/23,75%/)).toBeInTheDocument();
  expect(screen.getAllByText(/ORACLE_QUERY_TIMEOUT/).length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole('button', { name: /Incidència #77/ }));
  expect(localStorage.getItem('e13db:selected-finding-id')).toBe('77');
  expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'e13db-open-finding', detail: { id: 77 } }));
});

test('l’execució manual és d’una sola lectura, té límit temporal i refresca historial', async () => {
  render(<OracleDiagnosticsView profiles={['DWH']} selectedProfile="DWH"/>);
  const execute = await screen.findByRole('button', { name: 'Executa el diagnòstic' });
  await waitFor(() => expect(execute).toBeEnabled());
  fireEvent.click(execute);
  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
  expect(axios.post).toHaveBeenCalledWith('/api/audit/oracle-diagnostics/run', expect.objectContaining({ profile: 'DWH', audit_run_id: expect.stringMatching(/^AUD-MAN-/) }), expect.objectContaining({ timeout: 300000, signal: expect.any(AbortSignal) }));
  expect((await screen.findAllByText(/diag-manual-2/)).length).toBeGreaterThan(0);
  expect(screen.getByText('Resultat', { exact: true })).toBeInTheDocument();
});

test('evita dobles execucions mentre la petició està pendent', async () => {
  let finish;
  axios.post.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  render(<OracleDiagnosticsView profiles={['DWH']} selectedProfile="DWH"/>);
  const execute = await screen.findByRole('button', { name: 'Executa el diagnòstic' });
  await waitFor(() => expect(execute).toBeEnabled());
  fireEvent.click(execute);
  fireEvent.click(screen.getByRole('button', { name: 'Executant el diagnòstic…' }));
  expect(axios.post).toHaveBeenCalledTimes(1);
  expect(screen.getAllByText(/Executant el diagnòstic…/).length).toBeGreaterThan(0);
  finish({ data: { audit_run_id: 'diag-finished', audit_state: 'SUCCESS', coverage_state: 'FULL', summary: { query_budget: 8 }, rule_results: [], diagnostic_observations: [] } });
  expect((await screen.findAllByText(/diag-finished/)).length).toBeGreaterThan(0);
});

test('Actualitza només consulta l’historial i els filtres redueixen observacions', async () => {
  render(<OracleDiagnosticsView profiles={['DWH']} selectedProfile="DWH"/>);
  await screen.findByText(/SID 128/);
  fireEvent.click(screen.getAllByText('APP_DATA')[0].closest('summary'));
  fireEvent.change(screen.getByRole('textbox', { name: 'Filtra per objecte o SQL_ID' }), { target: { value: 'APP_DATA' } });
  expect(screen.getAllByText(/Ocupació de l’espai assignat/).length).toBeGreaterThan(0);
  expect(screen.queryByText(/SID 128/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Actualitza' }));
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith(expect.stringContaining('/history'), expect.objectContaining({ params: { limit: 50, offset: 0 } })));
  expect(axios.post).not.toHaveBeenCalled();
});

test('un error de xarxa surt de l’estat executant i es pot tornar a executar', async () => {
  axios.post.mockRejectedValue({ code: 'ECONNABORTED' });
  render(<OracleDiagnosticsView profiles={['DWH']} selectedProfile="DWH"/>);
  const execute = await screen.findByRole('button', { name: 'Executa el diagnòstic' });
  await waitFor(() => expect(execute).toBeEnabled());
  fireEvent.click(execute);
  expect(await screen.findByRole('alert')).toHaveTextContent('cinc minuts');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Executa el diagnòstic' })).toBeEnabled());
});

test('sense execució disponible i amb manca de capacitat mostra desconegut, no un fals zero', async () => {
  axios.get.mockImplementation(async (url) => url.includes('/history') ? { data: history([], null, 0, 0) } : { data: { items: [] } });
  render(<OracleDiagnosticsView profiles={['DWH']} selectedProfile="DWH"/>);
  expect(await screen.findByText(/Disponible \(AVAILABLE\)/)).toBeInTheDocument();
  expect(screen.getByText(/Encara no hi ha observacions/)).toBeInTheDocument();
});

test('una consulta fallida no es presenta com una execució completament correcta encara que l’API marqui cobertura completa', async () => {
  const inconsistent = { ...detail, coverage_state: 'FULL', summary: { query_count: 1, query_metrics: [{ rule_id: 'ORACLE_CAPACITY', status: 'ERROR' }] }, rule_results: [] };
  axios.get.mockImplementation(async (url) => url.includes('/history') ? { data: history([blocker], inconsistent, 0, 1) } : { data: { items: [] } });
  render(<OracleDiagnosticsView profiles={['DWH']} selectedProfile="DWH"/>);
  expect((await screen.findAllByText(/Parcial \(PARTIAL\)/)).length).toBeGreaterThan(0);
});
