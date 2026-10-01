import axios from 'axios';

export const getInvestigations = (params = {}) => axios.get('/api/investigations', { params }).then((r) => r.data);
export const getInvestigation = (id) => axios.get(`/api/investigations/${id}`).then((r) => r.data);
export const openInvestigation = (database_id, finding_id) => axios.post('/api/investigations', { database_id, finding_id }).then((r) => r.data);
export const setInvestigationStatus = (id, status) => axios.post(`/api/investigations/${id}/status`, { status }).then((r) => r.data);
export const confirmInvestigationCause = (id, description, evidence = []) => axios.post(`/api/investigations/${id}/cause`, { description, evidence }).then((r) => r.data);
export const recordInvestigationResolution = (id, resolution, actions_taken = '') => axios.post(`/api/investigations/${id}/resolution`, { resolution, actions_taken }).then((r) => r.data);
export const updateInvestigationCheck = (id, check_id, status, result_summary = '') => axios.post(`/api/investigations/${id}/checks/${check_id}`, { status, result_summary }).then((r) => r.data);
export const updateInvestigationHypothesis = (id, hypothesis_id, status) => axios.post(`/api/investigations/${id}/hypotheses/${hypothesis_id}`, { status }).then((r) => r.data);
export const getCapacityProjection = (id, evidence_id) => axios.get(`/api/investigations/${id}/capacity-projection/${evidence_id}`).then((r) => r.data);
