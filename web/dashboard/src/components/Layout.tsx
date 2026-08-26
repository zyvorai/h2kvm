// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { useState, useCallback, useEffect, useMemo } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/auth';
import { type WSMessage, useWebSocketConnected, useWebSocketSubscription } from '../contexts/WebSocketContext';
import { showToast } from './Toast';
import { useSessionTimeout } from '../hooks/useSessionTimeout';
import { ZyvorFooter } from './ZyvorBrand';
import { recordNavRecent, getNavRecents, filterNavRecents } from '../lib/navRecents';
import HelpDialog, { type HelpTab } from './HelpDialog';
import { CommandPalette, type CommandPaletteItem } from './CommandPalette';
import { DesktopLayout } from '../desktop/DesktopLayout';
import { ThemeProvider } from '../contexts/ThemeContext';
import { useDesktopTier } from '../hooks/useDesktopTier';
import {
  defaultViewForTier,
  ensureTierForView,
  isViewAllowedForTier,
} from '../lib/desktopTier';
import { dispatchOpenMissionControl } from '../desktop/MissionControlContext';
import {
  getNavGroups,
  pathFromView,
  viewFromPath,
  validNavPaths,
  type H2kView,
} from '../navigation/h2kNav';

export function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { username, logout } = useAuthStore();
  const [tier, setTier] = useDesktopTier();
  const currentView = viewFromPath(location.pathname);
  const [helpOpen, setHelpOpen] = useState(false);
  const [helpTab, setHelpTab] = useState<HelpTab>('about');
  const wsConnected = useWebSocketConnected();
  const [navRecents, setNavRecents] = useState(getNavRecents);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [serverVersion, setServerVersion] = useState<string | undefined>();

  useSessionTimeout();

  const trackNav = useCallback((path: string, label: string) => {
    recordNavRecent(path, label);
    setNavRecents(getNavRecents());
  }, []);

  const goToPath = useCallback(
    (path: string, label: string) => {
      trackNav(path, label);
      navigate(path);
    },
    [navigate, trackNav],
  );

  const goToView = useCallback(
    (view: H2kView) => {
      const nextTier = ensureTierForView(view, tier);
      if (nextTier !== tier) setTier(nextTier);
      const path = pathFromView(view);
      const label = getNavGroups().flatMap((g) => g.items).find((i) => i.id === view)?.label ?? view;
      goToPath(path, label);
    },
    [goToPath, tier, setTier],
  );

  const commandItems = useMemo((): CommandPaletteItem[] => {
    const actions: CommandPaletteItem[] = [
      {
        id: 'action-migrate',
        label: 'Start migration',
        group: 'Actions',
        keywords: 'export convert hub',
        onSelect: () => goToView('migrate'),
      },
      {
        id: 'action-providers',
        label: 'Connect provider',
        group: 'Actions',
        keywords: 'vsphere azure',
        onSelect: () => goToView('providers'),
      },
      {
        id: 'action-jobs',
        label: 'Open job monitor',
        group: 'Actions',
        keywords: 'progress logs',
        onSelect: () => goToView('jobmonitor'),
      },
      {
        id: 'action-help',
        label: 'Keyboard shortcuts',
        group: 'Actions',
        keywords: 'help',
        onSelect: () => {
          setHelpTab('shortcuts');
          setHelpOpen(true);
        },
      },
    ];
    const nav = getNavGroups().flatMap((group) =>
      group.items.map((item) => ({
        id: `nav-${item.path}`,
        label: item.label,
        group: group.label,
        keywords: item.path,
        onSelect: () => goToPath(item.path, item.label),
      })),
    );
    return [...actions, ...nav];
  }, [goToPath, goToView]);

  const filteredNavRecents = useMemo(
    () => filterNavRecents(navRecents, validNavPaths),
    [navRecents],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setCommandPaletteOpen((open) => !open);
        return;
      }
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (commandPaletteOpen) return;
      if (e.key === '?' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        setHelpTab('shortcuts');
        setHelpOpen(true);
        return;
      }
      if (e.key === 'Escape') {
        setCommandPaletteOpen(false);
        setHelpOpen(false);
        return;
      }
      if (e.key === 'F3') {
        e.preventDefault();
        dispatchOpenMissionControl();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [commandPaletteOpen]);

  useEffect(() => {
    if (!isViewAllowedForTier(currentView, tier)) {
      navigate(pathFromView(defaultViewForTier(tier)), { replace: true });
    }
  }, [tier, currentView, navigate]);

  useEffect(() => {
    fetch('/api/v1/health')
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { version?: string } | null) => {
        if (data?.version) setServerVersion(data.version);
      })
      .catch(() => {});
  }, []);

  useWebSocketSubscription(useCallback((msg: WSMessage) => {
    const jobId = (msg.data?.job_id as string) || '';
    const eventMessages: Record<string, { type: 'success' | 'error' | 'info'; text: string }> = {
      job_created: { type: 'info', text: `Migration ${jobId} queued` },
      job_started: { type: 'info', text: `Migration ${jobId} started` },
      job_completed: { type: 'success', text: `Migration ${jobId} completed successfully` },
      job_failed: { type: 'error', text: `Migration ${jobId} failed: ${msg.data?.error || 'unknown'}` },
      job_cancelled: { type: 'info', text: `Migration ${jobId} cancelled` },
    };
    const toast = eventMessages[msg.type];
    if (toast) showToast(toast.type, toast.text);
  }, []));

  const handleLogout = async () => {
    await logout();
    window.location.reload();
  };

  const openAbout = useCallback(() => {
    const nextTier = ensureTierForView('about', tier);
    if (nextTier !== tier) setTier(nextTier);
    navigate('/about');
  }, [navigate, tier, setTier]);

  return (
    <ThemeProvider>
      <DesktopLayout
        currentView={currentView}
        currentPath={location.pathname}
        navRecents={filteredNavRecents}
        onNavigate={goToView}
        onNavigatePath={(path) => {
          const view = viewFromPath(path);
          const nextTier = ensureTierForView(view, tier);
          if (nextTier !== tier) setTier(nextTier);
          const item = getNavGroups().flatMap((g) => g.items).find((i) => i.path === path);
          goToPath(path, item?.label ?? path);
        }}
        onOpenSpotlight={() => setCommandPaletteOpen(true)}
        onOpenHelp={() => { setHelpTab('shortcuts'); setHelpOpen(true); }}
        onOpenAbout={openAbout}
        onLogout={handleLogout}
        displayUsername={username ?? 'admin'}
        wsConnected={wsConnected}
        serverVersion={serverVersion}
      >
        <div className="animate-fade-in flex-1 flex flex-col min-h-0">
          <Outlet />
          <ZyvorFooter className="mt-auto pt-6" />
        </div>
      </DesktopLayout>

      <CommandPalette
        open={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        items={commandItems}
      />
      <HelpDialog
        open={helpOpen}
        tab={helpTab}
        onClose={() => setHelpOpen(false)}
        onTabChange={setHelpTab}
      />
    </ThemeProvider>
  );
}
