import axios from 'axios';

export async function runOracleDiagnostics(payload, config = {}) {
  const response = await axios.post('/api/audit/oracle-diagnostics/run', payload || {}, config);
  return response.data;
}

export async function getOracleDiagnosticHistory(databaseId, params = {}) {
  const response = await axios.get(`/api/oracle-diagnostics/${encodeURIComponent(databaseId)}/history`, { params });
  return response.data;
}

export async function getAuditRun(auditRunId) {
  const response = await axios.get(`/api/audit-runs/${encodeURIComponent(auditRunId)}`);
  return response.data;
}
