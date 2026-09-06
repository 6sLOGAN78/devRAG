import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { getToken, setToken, removeToken, TOKEN_KEY, apiClient } from './authorization-util';
import { useAuthStore } from '../stores/auth-store';
import MockAdapter from 'axios-mock-adapter';

describe('authorization-util', () => {
  let mockAxios: MockAdapter;

  beforeEach(() => {
    localStorage.clear();
    mockAxios = new MockAdapter(apiClient);
    
    // Reset window.location
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { pathname: '/dashboard', href: '/dashboard' }
    });
  });

  afterEach(() => {
    mockAxios.restore();
    vi.clearAllMocks();
  });

  it('sets, gets, and removes token from localStorage', () => {
    expect(getToken()).toBeNull();
    setToken('test-token');
    expect(getToken()).toBe('test-token');
    expect(localStorage.getItem(TOKEN_KEY)).toBe('test-token');
    
    removeToken();
    expect(getToken()).toBeNull();
  });

  it('attaches token to request if present', async () => {
    setToken('test-auth-token');
    mockAxios.onGet('/test').reply(200);

    const response = await apiClient.get('/test');
    expect(response.config.headers?.Authorization).toBe('Bearer test-auth-token');
  });

  it('does not attach Authorization header if no token', async () => {
    removeToken();
    mockAxios.onGet('/test').reply(200);

    const response = await apiClient.get('/test');
    expect(response.config.headers?.Authorization).toBeUndefined();
  });

  it('handles 401 response and triggers logout', async () => {
    setToken('invalid-token');
    mockAxios.onGet('/protected').reply(401);

    const logoutSpy = vi.spyOn(useAuthStore.getState(), 'logout');

    try {
      await apiClient.get('/protected');
    } catch (e) {
      // Expected to fail
    }

    expect(getToken()).toBeNull();
    expect(logoutSpy).toHaveBeenCalled();
    expect(window.location.href).toBe('/login');
  });

  it('does not trigger logout for 401 on login endpoint', async () => {
    setToken('valid-token');
    mockAxios.onPost('/user/login').reply(401);

    const logoutSpy = vi.spyOn(useAuthStore.getState(), 'logout');

    try {
      await apiClient.post('/user/login', {});
    } catch (e) {
      // Expected
    }

    // Token should still be there because it was a login attempt
    expect(getToken()).toBe('valid-token');
    expect(logoutSpy).not.toHaveBeenCalled();
    expect(window.location.href).not.toBe('/login');
  });
});
