import React from 'react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import axios from 'axios';
import OracleDiagnosticsView from './OracleDiagnosticsView.jsx';

vi.mock('axios',()=>({default:{get:vi.fn(),post:vi.fn()}}));

const blocker={
  audit_run_id:'diag-1',database_id:'DWH',category:'BLOCKING',identity_key:'inst=1:con=5:sid=128:serial=900',
  observed_at:1800000000,inst_id:1,con_id:5,metrics:{affected_sessions:3,chain_depth:2,observed_duration_seconds:120,sample_count:2},
  evidence:{root_blocker:'inst=1:con=5:sid=128:serial=900',root_blocker_name:'APP',observation_note:'Observed across snapshots.',chain:[{blocking_instance:1,blocking_session:128,blocked_instance:2,blocked_session:244,wait_class:'Application',event:'enq: TX',wait_seconds:60}]},
};
const detail={audit_run_id:'diag-1',state:'SUCCESS',coverage_state:'FULL',reconciliation_state:'RECONCILED',trigger_type:'SCHEDULED',runtime_identity:{git_sha:'fixture'},execution_options:{tablespace_warning_percent:80,tablespace_critical_percent:95},rule_results:[{rule_id:'ORACLE_BLOCKING',status:'FAIL',summary:'Root blocker affects 3 sessions',coverage_meaning:'evaluated'}],capability_snapshot:{snapshot_id:'cap-1',snapshot_hash:'cap-hash',snapshot:{capabilities:{SESSION_VISIBILITY:'AVAILABLE',LOCK_VISIBILITY:'AVAILABLE',AWR_ALLOWED:'NOT_LICENSED',ASH_ALLOWED:'NOT_LICENSED'},reasons:{SESSION_VISIBILITY:'Read-only metadata probe succeeded.'},connection_class:'AVAILABLE',rac_instance_count:2,cdb_mode:'CDB',current_container_id:5,license_gates:{disclosure:'AWR/ASH views are not queried.'}}}};

beforeEach(()=>{
  localStorage.clear();
  axios.get.mockImplementation(async(url)=>{
    if(url.includes('/history')) return {data:{items:[blocker]}};
    if(url==='/api/findings') return {data:{items:[{id:77,database_id:'DWH',rule_id:'ORACLE_BLOCKING',object_name:blocker.identity_key,severity:'CRITICAL',delta:'NEW',status:'OPEN',evidence:JSON.stringify({sql_id:'SQLA'})}]}};
    if(url==='/api/audit-runs/diag-1') return {data:detail};
    throw new Error(`Unexpected GET ${url}`);
  });
  axios.post.mockResolvedValue({data:{audit_run_id:'diag-manual-2',coverage_state:'FULL',reconciliation_state:'RECONCILED',capability_snapshot:{capabilities:{AWR_ALLOWED:'NOT_LICENSED',ASH_ALLOWED:'NOT_LICENSED'}},rule_results:[],diagnostic_observations:[blocker],finding_envelopes:[]}});
});

afterEach(()=>{cleanup();vi.clearAllMocks();});

test('operator sees scoped capability coverage, blocking evidence, and a direct Finding link',async()=>{
  const dispatch=vi.spyOn(window,'dispatchEvent');
  render(<OracleDiagnosticsView profiles={['DWH']} selectedProfile="DWH"/>);
  expect(await screen.findByText(/SID 128/)).toBeInTheDocument();
  expect(screen.getByText(/enq: TX/)).toBeInTheDocument();
  expect(screen.getByText(/RAC instances: 2/)).toBeInTheDocument();
  expect(screen.getByText(/NOT_LICENSED \/ NOT_LICENSED/)).toBeInTheDocument();
  expect(screen.getByText(/tablespace warning percent: 80/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:/Finding #77/}));
  expect(localStorage.getItem('e13db:selected-finding-id')).toBe('77');
  expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({type:'e13db-open-finding',detail:{id:77}}));
});

test('manual diagnostic execution sends one stable AuditRun ID and refreshes evidence',async()=>{
  render(<OracleDiagnosticsView profiles={['DWH']} selectedProfile="DWH"/>);
  await screen.findByText(/SID 128/);
  fireEvent.click(screen.getByRole('button',{name:/Run read-only diagnostics/i}));
  await waitFor(()=>expect(axios.post).toHaveBeenCalledWith('/api/audit/oracle-diagnostics/run',expect.objectContaining({profile:'DWH',audit_run_id:expect.stringMatching(/^AUD-MAN-/)})));
  expect(await screen.findByText(/diag-manual-2/)).toBeInTheDocument();
});
