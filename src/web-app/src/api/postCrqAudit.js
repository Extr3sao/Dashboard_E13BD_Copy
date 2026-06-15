import axios from 'axios';

const API_BASE = '/api';

export async function listPostCrqChecks() {
  const res = await axios.get(`${API_BASE}/audit/post-crq/checks`);
  return res.data;
}

export async function runPostCrqAudit(payload) {
  const res = await axios.post(`${API_BASE}/audit/post-crq/run`, payload || {});
  return res.data;
}

export async function downloadPostCrqReport(payload) {
  const res = await axios.post(`${API_BASE}/audit/post-crq/reports`, payload || {}, {
    responseType: 'blob',
  });
  return res;
}
