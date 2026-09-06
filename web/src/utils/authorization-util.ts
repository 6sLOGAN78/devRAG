import axios, { AxiosError } from 'axios';
import { useAuthStore } from '../stores/auth-store';

export const TOKEN_KEY = 'devrag_auth_token';

export const getToken = (): string | null => {
  return localStorage.getItem(TOKEN_KEY);
};

export const setToken = (token: string): void => {
  localStorage.setItem(TOKEN_KEY, token);
};

export const removeToken = (): void => {
  localStorage.removeItem(TOKEN_KEY);
};

export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
});

apiClient.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Avoid redirect loops if it's a login/register request
      const isAuthEndpoint = error.config?.url?.includes('/user/login') || error.config?.url?.includes('/user/register');
      
      if (!isAuthEndpoint) {
        removeToken();
        const { logout } = useAuthStore.getState();
        logout();
        // Redirect to login using window.location for hard reset, or standard router
        if (window.location.pathname !== '/login') {
            window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);
