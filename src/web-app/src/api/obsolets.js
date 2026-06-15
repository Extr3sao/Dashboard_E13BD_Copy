import axios from 'axios';

const API_BASE = '/api';

export async function listObsolets(params) {
  const res = await axios.get(`${API_BASE}/obsolets`, { params: params || {} });
  return res.data;
}

export async function createObsolet(payload) {
  const res = await axios.post(`${API_BASE}/obsolets`, payload);
  return res.data;
}

export async function updateObsolet(id, payload) {
  const res = await axios.patch(`${API_BASE}/obsolets/${id}`, payload);
  return res.data;
}

