import axios from 'axios';

const API_BASE = '/api/docs/post-crq-operational';

export async function listPostCrqOperationalDocuments() {
  const res = await axios.get(API_BASE);
  return res.data;
}

export async function listPostCrqOperationalDocumentHistory(documentId, params = {}) {
  const res = await axios.get(`${API_BASE}/${documentId}/history`, { params });
  return res.data;
}

export async function updatePostCrqOperationalDocument(documentId, payload) {
  const res = await axios.put(`${API_BASE}/${documentId}`, payload);
  return res.data;
}
