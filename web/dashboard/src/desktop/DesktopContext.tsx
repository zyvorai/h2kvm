// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { defaultSidebarVisibleForTier, DESKTOP_TIER_EVENT, loadDesktopTier } from '../lib/desktopTier';

interface DesktopContextType {
  sidebarVisible: boolean;
  sidebarCollapsed: boolean;
  setSidebarVisible: (v: boolean) => void;
  setSidebarCollapsed: (v: boolean) => void;
  toggleSidebar: () => void;
}

const DesktopContext = createContext<DesktopContextType>({
  sidebarVisible: true,
  sidebarCollapsed: false,
  setSidebarVisible: () => {},
  setSidebarCollapsed: () => {},
  toggleSidebar: () => {},
});

export function DesktopProvider({ children }: { children: ReactNode }) {
  const [sidebarVisible, setSidebarVisible] = useState(() => defaultSidebarVisibleForTier(loadDesktopTier()));
  const [sidebarCollapsed, setSidebarCollapsedState] = useState(() => {
    try { return localStorage.getItem('h2kweb-sidebar-collapsed') === '1'; } catch { return false; }
  });

  const setSidebarCollapsed = useCallback((v: boolean) => {
    setSidebarCollapsedState(v);
    try { localStorage.setItem('h2kweb-sidebar-collapsed', v ? '1' : '0'); } catch { /* ignore */ }
  }, []);

  const toggleSidebar = useCallback(() => {
    setSidebarVisible((vis) => !vis);
  }, []);

  useEffect(() => {
    const onTierChange = () => {
      setSidebarVisible(defaultSidebarVisibleForTier(loadDesktopTier()));
    };
    window.addEventListener(DESKTOP_TIER_EVENT, onTierChange);
    return () => window.removeEventListener(DESKTOP_TIER_EVENT, onTierChange);
  }, []);

  return (
    <DesktopContext.Provider
      value={{ sidebarVisible, sidebarCollapsed, setSidebarVisible, setSidebarCollapsed, toggleSidebar }}
    >
      {children}
    </DesktopContext.Provider>
  );
}

export function useDesktop() {
  return useContext(DesktopContext);
}
