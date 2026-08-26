// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { create } from 'zustand';
import * as authApi from '../api/auth';

interface AuthState {
  isAuthenticated: boolean;
  username: string;
  loading: boolean;
  error: string | null;
  checkSession: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  isAuthenticated: false,
  username: '',
  loading: true,
  error: null,

  checkSession: async () => {
    try {
      const session = await authApi.getSession();
      set({
        isAuthenticated: session.authenticated,
        username: session.username || '',
        loading: false,
      });
    } catch {
      set({ isAuthenticated: false, username: '', loading: false });
    }
  },

  login: async (username: string, password: string) => {
    set({ error: null });
    try {
      await authApi.login(username, password);
      set({ isAuthenticated: true, username, error: null });
    } catch (err) {
      set({ error: (err as Error).message });
      throw err;
    }
  },

  logout: async () => {
    await authApi.logout();
    set({ isAuthenticated: false, username: '' });
  },
}));
