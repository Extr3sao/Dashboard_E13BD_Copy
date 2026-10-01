import axios from 'axios';
export const getAlerts = (params = {}) => axios.get('/api/alerting/alerts', { params }).then((r) => r.data);
export const getNotificationHealth = () => axios.get('/api/alerting/notification-health').then((r) => r.data);
export const alertAction = (id, action, payload) => axios.post(`/api/alerting/alerts/${id}/${action}`, payload).then((r) => r.data);
export const getReports = () => axios.get('/api/alerting/reports').then((r) => r.data);
export const generateReport = (type) => axios.post(`/api/alerting/reports/${type}`).then((r) => r.data);
export const getReport = (id) => axios.get(`/api/alerting/reports/${id}`).then((r) => r.data);
export const deliverReport = (id) => axios.post(`/api/alerting/reports/${id}/deliver`).then((r) => r.data);
