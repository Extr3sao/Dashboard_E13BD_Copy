import axios from 'axios';

const API_BASE = '/api';

export async function listSnapshots() {
  const res = await axios.get(`${API_BASE}/snapshots`);
  return res.data;
}

export async function latestSnapshot() {
  const res = await axios.get(`${API_BASE}/snapshots/latest`);
  return res.data;
}

export async function querySnapshot(payload) {
  const res = await axios.post(`${API_BASE}/snapshots/query`, payload || {});
  return res.data;
}

export async function exportSnapshotCsv(payload) {
  const res = await axios.post(`${API_BASE}/snapshots/export.csv`, payload || {}, { responseType: 'blob' });
  return res;
}

