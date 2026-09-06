import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useAuthStore } from './auth-store';
import { setToken, getToken, apiClient } from '../utils/authorization-util';
import MockAdapter from 'axios-mock-adapter';

describe('auth-store', () => {
  let mockAxios: MockAdapter;

  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({ user: null, isAuthenticated: false, isHydrating: true });
    mockAxios = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mockAxios.restore();
    vi.clearAllMocks();
  });

  it('login sets token and state', () => {
    const { login } = useAuthStore.getState();
    const user = { id: '1', email: 'test@test.com', nickname: 'Test' };
    
    login('token123', user);
    
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.user).toEqual(user);
    expect(getToken()).toBe('token123');
  });

  it('logout removes token and state', () => {
    const { login, logout } = useAuthStore.getState();
    const user = { id: '1', email: 'test@test.com', nickname: 'Test' };
    login('token123', user);
    
    logout();
    
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.user).toBeNull();
    expect(getToken()).toBeNull();
  });

  it('hydrate works when token exists and backend returns user', async () => {
    setToken('token123');
    const user = { id: '2', email: 'hydrate@test.com', nickname: 'Hydrated' };
    mockAxios.onGet('/user/info').reply(200, { user });

    const { hydrate } = useAuthStore.getState();
    await hydrate();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.isHydrating).toBe(false);
    expect(state.user).toEqual(user);
  });

  it('hydrate fails cleanly if backend rejects token', async () => {
    setToken('bad-token');
    mockAxios.onGet('/user/info').reply(401);

    const { hydrate } = useAuthStore.getState();
    await hydrate();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isHydrating).toBe(false);
    expect(state.user).toBeNull();
    expect(getToken()).toBeNull();
  });
});
