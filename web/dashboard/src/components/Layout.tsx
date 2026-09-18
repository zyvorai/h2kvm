// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
// https://zyvor.dev · info@zyvor.dev

import { useState, useCallback, useEffect, useMemo } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { type WSMessage, useWebSocketSubscription } from '../contexts/WebSocketContext';
import { showToast } from './Toast';
import { useSessionTimeout } from '../hooks/useSessionTimeout';
import HelpDialog, { type HelpTab } from './HelpDialog';
import { CommandPalette, type CommandPaletteItem } from './CommandPalette';
import { ThemeProvider } from '../contexts/ThemeContext';
import { ConsoleLayout } from './console/ConsoleLayout';
import { getNavGroups, navLabelForView, viewFromPath, type H2kView } from '../navigation/h2kNav';

export function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [helpOpen, setHelpOpen] = useState(false);
  const [helpTab, setHelpTab] = useState<HelpTab>('about');
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const currentView = viewFromPath(location.pathname);

  useSessionTimeout();

  const goToView = useCallback(
    (view: H2kView) => {
      const path = getNavGroups().flatMap((g) => g.items).find((i) => i.id === view)?.path ?? '/';
      navigate(path);
    },
    [navigate],
  );

  const commandItems = useMemo((): CommandPaletteItem[] => {
    const actions: CommandPaletteItem[] = [
      { id: 'action-migrate', label: 'Start migration', group: 'Actions', keywords: 'export convert', onSelect: () => goToView('migrate') },
      { id: 'action-providers', label: 'Connect provider', group: 'Actions', keywords: 'vsphere azure', onSelect: () => goToView('providers') },
      { id: 'action-jobs', label: 'Open job monitor', group: 'Actions', keywords: 'progress logs', onSelect: () => goToView('jobmonitor') },
      {
        id: 'action-help',
        label: 'Keyboard shortcuts',
        group: 'Actions',
        keywords: 'help',
        onSelect: () => { setHelpTab('shortcuts'); setHelpOpen(true); },
      },
    ];
    const nav = getNavGroups().flatMap((group) =>
      group.items.map((item) => ({
        id: `nav-${item.path}`,
        label: item.label,
        group: group.label,
        keywords: item.path,
        onSelect: () => navigate(item.path),
      })),
    );
    return [...actions, ...nav];
  }, [goToView, navigate]);

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
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [commandPaletteOpen]);

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

  return (
    <ThemeProvider>
      <ConsoleLayout
        realm={navLabelForView(currentView)}
        onOpenPalette={() => setCommandPaletteOpen(true)}
      >
        <Outlet />
      </ConsoleLayout>
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
