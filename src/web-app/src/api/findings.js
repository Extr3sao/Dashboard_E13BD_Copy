import axios from 'axios';

export async function getNeedsAttention(params = {}) {
  const response = await axios.get('/api/findings/needs-attention', { params });
  return response.data;
}

export async function getFindings(params = {}) {
  const response = await axios.get('/api/findings', { params });
  return response.data;
}

export async function getFinding(id) {
  const response = await axios.get(`/api/findings/${id}`);
  return response.data;
}

export async function applyFindingAction(id, action, payload) {
  const response = await axios.post(`/api/findings/${id}/${action}`, payload);
  return response.data;
}
