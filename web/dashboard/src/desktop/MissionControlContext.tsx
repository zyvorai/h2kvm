// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

export const OPEN_MISSION_CONTROL_EVENT = 'h2k-open-mission-control';

function initialMissionControlOpen(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    if (new URLSearchParams(window.location.search).get('mission') === '1') return true;
    return sessionStorage.getItem('h2kweb-open-mission') === '1';
  } catch {
    return false;
  }
}

type MissionControlContextValue = {
  open: boolean;
  openMissionControl: () => void;
  closeMissionControl: () => void;
  toggleMissionControl: () => void;
};

const MissionControlContext = createContext<MissionControlContextValue | null>(null);

export function MissionControlProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(initialMissionControlOpen);

  const openMissionControl = useCallback(() => {
    try { sessionStorage.setItem('h2kweb-open-mission', '1'); } catch { /* ignore */ }
    setOpen(true);
  }, []);

  const closeMissionControl = useCallback(() => {
    try { sessionStorage.removeItem('h2kweb-open-mission'); } catch { /* ignore */ }
    setOpen(false);
  }, []);

  const toggleMissionControl = useCallback(() => setOpen((v) => !v), []);

  const value = useMemo(
    () => ({ open, openMissionControl, closeMissionControl, toggleMissionControl }),
    [open, openMissionControl, closeMissionControl, toggleMissionControl],
  );

  return <MissionControlContext.Provider value={value}>{children}</MissionControlContext.Provider>;
}

export function useMissionControl() {
  const ctx = useContext(MissionControlContext);
  if (!ctx) throw new Error('useMissionControl must be used within MissionControlProvider');
  return ctx;
}

export function dispatchOpenMissionControl() {
  window.dispatchEvent(new CustomEvent(OPEN_MISSION_CONTROL_EVENT));
}
