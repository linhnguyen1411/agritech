import axios from 'axios';
import type { AxiosInstance, AxiosRequestConfig } from 'axios';

export function createApiClient(baseURL: string, config?: AxiosRequestConfig): AxiosInstance {
  const client = axios.create({
    baseURL,
    headers: { 'Content-Type': 'application/json' },
    ...config,
  });

  client.interceptors.request.use((req) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    if (token) {
      req.headers.Authorization = `Bearer ${token}`;
    }
    return req;
  });

  client.interceptors.response.use(
    (res) => res,
    (err: unknown) => {
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        if (typeof window !== 'undefined') {
          localStorage.removeItem('access_token');
        }
      }
      return Promise.reject(err);
    },
  );

  return client;
}

const defaultBaseUrl = 'http://localhost:8000';

export const apiClient = createApiClient(defaultBaseUrl);
