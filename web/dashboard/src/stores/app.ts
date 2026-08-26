// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { create } from 'zustand';
import type { JobStats } from '../types/job';

interface AppState {
  wsConnected: boolean;
  setWsConnected: (connected: boolean) => void;

  jobStats: JobStats | null;
  setJobStats: (stats: JobStats) => void;

  selectedProvider: string | null;
  setSelectedProvider: (id: string | null) => void;

  selectedVMs: string[];
  toggleVM: (id: string) => void;
  clearSelectedVMs: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  wsConnected: false,
  setWsConnected: (connected) => set({ wsConnected: connected }),

  jobStats: null,
  setJobStats: (stats) => set({ jobStats: stats }),

  selectedProvider: null,
  setSelectedProvider: (id) => set({ selectedProvider: id }),

  selectedVMs: [],
  toggleVM: (id) =>
    set((state) => ({
      selectedVMs: state.selectedVMs.includes(id)
        ? state.selectedVMs.filter((v) => v !== id)
        : [...state.selectedVMs, id],
    })),
  clearSelectedVMs: () => set({ selectedVMs: [] }),
}));
