import axios from 'axios';

let csrfToken = null;
let unauthorizedHandler = null;

export function setCsrfToken(token) {
  csrfToken = token || null;
}

export function configureApiSecurity(onUnauthorized) {
  unauthorizedHandler = onUnauthorized;
  axios.defaults.withCredentials = true;
  axios.interceptors.request.use((config) => {
    if (csrfToken && !['get', 'head', 'options'].includes(String(config.method || 'get').toLowerCase())) {
      config.headers = { ...(config.headers || {}), 'X-CSRF-Token': csrfToken };
    }
    return config;
  });
  axios.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error?.response?.status === 401) {
        csrfToken = null;
        unauthorizedHandler?.();
      }
      return Promise.reject(error);
    },
  );
}

export async function getCurrentUser() {
  const response = await axios.get('/auth/me');
  setCsrfToken(response.data?.csrf_token);
  return response.data;
}

export async function login(username, password) {
  const response = await axios.post('/auth/login', { username, password });
  setCsrfToken(response.data?.csrf_token);
  return response.data;
}

export async function logout() {
  await axios.post('/auth/logout');
  setCsrfToken(null);
}
