import axios from 'axios';

const API_BASE = '/api/automation';

export async function listAutomationJobs() {
  const res = await axios.get(`${API_BASE}/jobs`);
  return res.data;
}

export async function createAutomationJob(payload) {
  const res = await axios.post(`${API_BASE}/jobs`, payload);
  return res.data;
}

export async function updateAutomationJob(jobId, payload) {
  const res = await axios.put(`${API_BASE}/jobs/${jobId}`, payload);
  return res.data;
}

export async function deleteAutomationJob(jobId) {
  const res = await axios.delete(`${API_BASE}/jobs/${jobId}`);
  return res.data;
}

export async function runAutomationJobNow(jobId) {
  const res = await axios.post(`${API_BASE}/jobs/${jobId}/run-now`);
  return res.data;
}

export async function listAutomationRuns(jobId = null, limit = 100) {
  const params = { limit };
  if (jobId) params.job_id = jobId;
  const res = await axios.get(`${API_BASE}/runs`, { params });
  return res.data;
}

export async function listAutomationRunLots(runId) {
  const res = await axios.get(`${API_BASE}/runs/${runId}/lots`);
  return res.data;
}

export async function listAutomationRunLotsFiltered(runId, params = {}) {
  const res = await axios.get(`${API_BASE}/runs/${runId}/lots`, { params });
  return res.data;
}

export async function getAutomationRunReportData(runId) {
  const res = await axios.get(`${API_BASE}/runs/${runId}/report-data`);
  return res.data;
}

export async function exportAutomationRunLotsCsv(runId, params = {}) {
  const res = await axios.get(`${API_BASE}/runs/${runId}/lots/export.csv`, {
    params,
    responseType: 'blob',
  });
  return res;
}

export function getAutomationRunReportUrl(runId) {
  return `${API_BASE}/runs/${runId}/report`;
}

export async function listAutomationTasks(status = null, limit = 200) {
  const params = { limit };
  if (status) params.status = status;
  const res = await axios.get(`${API_BASE}/tasks`, { params });
  return res.data;
}

export async function updateAutomationTask(taskId, payload) {
  const res = await axios.put(`${API_BASE}/tasks/${taskId}`, payload);
  return res.data;
}

export async function listSeverityRules(scope = null, jobId = null) {
  const params = {};
  if (scope) params.scope = scope;
  if (jobId) params.job_id = jobId;
  const res = await axios.get(`${API_BASE}/severity-rules`, { params });
  return res.data;
}

export async function createSeverityRule(payload) {
  const res = await axios.post(`${API_BASE}/severity-rules`, payload);
  return res.data;
}

export async function updateSeverityRule(ruleId, payload) {
  const res = await axios.put(`${API_BASE}/severity-rules/${ruleId}`, payload);
  return res.data;
}

export async function getDeliveryConfig() {
  const res = await axios.get(`${API_BASE}/delivery-config`);
  return res.data;
}

export async function updateDeliveryConfig(payload) {
  const res = await axios.put(`${API_BASE}/delivery-config`, payload);
  return res.data;
}

export async function getDeliveryRoutes() {
  const res = await axios.get(`${API_BASE}/delivery-routes`);
  return res.data;
}

export async function updateDeliveryRoutes(payload) {
  const res = await axios.put(`${API_BASE}/delivery-routes`, payload);
  return res.data;
}

export async function listMasterLots(enabledOnly = false) {
  const res = await axios.get(`${API_BASE}/master-lots`, { params: { enabled_only: enabledOnly } });
  return res.data;
}

export async function listSchemaLots() {
  const res = await axios.get(`${API_BASE}/schema-lots`);
  return res.data;
}

export async function updateSchemaLots(payload) {
  const res = await axios.put(`${API_BASE}/schema-lots`, payload);
  return res.data;
}

export async function updateMasterLots(payload) {
  const res = await axios.put(`${API_BASE}/master-lots`, payload);
  return res.data;
}

export async function listMasterLotBackfillRuns(limit = 20) {
  const res = await axios.get(`${API_BASE}/master-lots/backfill-runs`, { params: { limit } });
  return res.data;
}

export async function previewMasterLotsBackfill(params = {}) {
  const res = await axios.get(`${API_BASE}/master-lots/backfill-preview`, { params });
  return res.data;
}

export async function applyMasterLotsBackfill(payload) {
  const res = await axios.post(`${API_BASE}/master-lots/backfill-apply`, payload);
  return res.data;
}

export async function listLotRoutes(audience = null) {
  const params = {};
  if (audience) params.audience = audience;
  const res = await axios.get(`${API_BASE}/lot-routes`, { params });
  return res.data;
}

export async function updateLotRoutes(payload) {
  const res = await axios.put(`${API_BASE}/lot-routes`, payload);
  return res.data;
}

export async function listDeliveryTemplates(audience = null) {
  const params = {};
  if (audience) params.audience = audience;
  const res = await axios.get(`${API_BASE}/delivery-templates`, { params });
  return res.data;
}

export async function updateDeliveryTemplates(payload) {
  const res = await axios.put(`${API_BASE}/delivery-templates`, payload);
  return res.data;
}

export async function listAutomationChangeEvents(params = {}) {
  const res = await axios.get(`${API_BASE}/change-events`, { params });
  return res.data;
}

export async function listDeliveryAttempts(params = {}) {
  const res = await axios.get(`${API_BASE}/delivery-attempts`, { params });
  return res.data;
}

export async function listRetryQueue(params = {}) {
  const res = await axios.get(`${API_BASE}/retry-queue`, { params });
  return res.data;
}

export async function getAutomationMaintenanceSummary(retainDays = 30) {
  const res = await axios.get(`${API_BASE}/maintenance/summary`, { params: { retain_days: retainDays } });
  return res.data;
}

export async function purgeAutomationHistory(payload) {
  const res = await axios.post(`${API_BASE}/maintenance/purge-history`, payload);
  return res.data;
}

export async function purgeAutomationRetryQueue(payload = {}) {
  const res = await axios.post(`${API_BASE}/maintenance/purge-retry-queue`, payload);
  return res.data;
}

export async function getAutomationAnalyticsOverview(month = null) {
  const params = {};
  if (month) params.month = month;
  const res = await axios.get(`${API_BASE}/analytics/overview`, { params });
  return res.data;
}

export async function listAutomationAnalyticsLots(month = null, limit = 100) {
  const params = { limit };
  if (month) params.month = month;
  const res = await axios.get(`${API_BASE}/analytics/lots`, { params });
  return res.data;
}

export async function listAutomationAnalyticsSchemas(month = null, limit = 100) {
  const params = { limit };
  if (month) params.month = month;
  const res = await axios.get(`${API_BASE}/analytics/schemas`, { params });
  return res.data;
}

export async function listAutomationAnalyticsChecks(month = null, limit = 100) {
  const params = { limit };
  if (month) params.month = month;
  const res = await axios.get(`${API_BASE}/analytics/checks`, { params });
  return res.data;
}

export async function exportAutomationAnalyticsMonthlyPdf(month = null, limit = 100) {
  const params = { limit };
  if (month) params.month = month;
  const res = await axios.get(`${API_BASE}/analytics/monthly-report.pdf`, {
    params,
    responseType: 'blob',
  });
  return res;
}

export async function enqueueRetry(payload) {
  const res = await axios.post(`${API_BASE}/retry-queue`, payload);
  return res.data;
}

export async function runRetryNow(queueId) {
  const res = await axios.post(`${API_BASE}/retry-queue/${queueId}/run-now`);
  return res.data;
}

export async function testDeliveryEmail(payload) {
  const res = await axios.post(`${API_BASE}/delivery-config/test-email`, payload);
  return res.data;
}
