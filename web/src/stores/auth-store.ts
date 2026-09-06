import { create } from 'zustand';
import { getToken, removeToken, setToken } from '../utils/authorization-util';
import { apiClient } from '../utils/authorization-util';

export interface User {
  id: string;
  email: string;
  nickname: string;
  tenant_id?: string;
  role?: string;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isHydrating: boolean;
  login: (token: string, user: User) => void;
  logout: () => void;
  setUser: (user: User) => void;
  hydrate: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isHydrating: true,

  login: (token: string, user: User) => {
    setToken(token);
    set({ user, isAuthenticated: true });
  },

  logout: () => {
    removeToken();
    set({ user: null, isAuthenticated: false });
  },

  setUser: (user: User) => {
    set({ user });
  },

  hydrate: async () => {
    const token = getToken();
    if (!token) {
      set({ user: null, isAuthenticated: false, isHydrating: false });
      return;
    }

    try {
      const response = await apiClient.get<{ user: User }>('/user/info');
      set({ user: response.data.user, isAuthenticated: true, isHydrating: false });
    } catch (error) {
      console.error('Failed to hydrate auth state:', error);
      removeToken();
      set({ user: null, isAuthenticated: false, isHydrating: false });
    }
  },
}));
