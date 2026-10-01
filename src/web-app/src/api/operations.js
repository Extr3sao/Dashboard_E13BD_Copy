import axios from 'axios';
export const getFleet = () => axios.get('/api/operations/fleet').then((r) => r.data);
export const getTarget = (id) => axios.get(`/api/operations/targets/${encodeURIComponent(id)}`).then((r) => r.data);
