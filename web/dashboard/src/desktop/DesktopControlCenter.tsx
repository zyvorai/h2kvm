// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { useEffect, useRef, useState } from 'react';
import { SlidersHorizontal, X, PanelLeft, LogOut, User } from 'lucide-react';
import { useTheme, type AppTheme, type DesktopWallpaper } from '../contexts/ThemeContext';
import { useDesktop } from './DesktopContext';
import { useDesktopTier } from '../hooks/useDesktopTier';
import { DesktopTierPicker } from './DesktopTierPicker';
import { dispatchOpenMissionControl } from './MissionControlContext';
import { DesktopLanguagePicker } from './DesktopLanguagePicker';
import { t } from '../i18n';

type Props = {
  displayUsername: string;
  onLogout: () => void;
  onOpenHelp: () => void;
};

const THEME_LABELS: Record<AppTheme, string> = {
  dark: 'Liquid Glass',
  steel: 'Steel',
  aurora: 'Aurora',
};

export function DesktopControlCenter({ displayUsername, onLogout, onOpenHelp }: Props) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const { theme, cycleTheme, wallpaper, setWallpaper } = useTheme();
  const { sidebarVisible, toggleSidebar } = useDesktop();
  const [tier, setTier] = useDesktopTier();

  useEffect(() => {
    if (!open) return;
    const onDocMouseDown = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDocMouseDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="relative z-[400]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center justify-center w-8 h-8 rounded-lg text-white/60 hover:text-white hover:bg-white/5 transition"
        title="Control Center"
        aria-label="Control Center"
        aria-expanded={open}
      >
        <SlidersHorizontal className="w-4 h-4" />
      </button>
      {open && (
        <div
          ref={panelRef}
          className="absolute right-0 top-full mt-2 w-72 rounded-2xl border border-white/10 glass-strong p-4 shadow-2xl z-50"
        >
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm font-semibold text-white/90">Control Center</p>
            <button type="button" onClick={() => setOpen(false)} className="p-1 rounded-lg hover:bg-white/5 text-white/50" aria-label="Close">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-white/60">Theme</span>
              <button type="button" onClick={cycleTheme} className="tahoe-btn-ghost text-xs py-1 px-2">
                {THEME_LABELS[theme]}
              </button>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-white/60">Wallpaper</span>
              <div className="flex gap-1">
                {(['tahoe', 'aurora'] as DesktopWallpaper[]).map((w) => (
                  <button
                    key={w}
                    type="button"
                    onClick={() => setWallpaper(w)}
                    className={`px-2 py-1 rounded-lg text-xs capitalize transition ${
                      wallpaper === w ? 'tahoe-context-pill-active' : 'text-white/50 hover:bg-white/5'
                    }`}
                  >
                    {w}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-white/60 mb-2">Desktop tier</p>
              <DesktopTierPicker tier={tier} onChange={setTier} compact />
            </div>
            <div>
              <p className="text-white/60 mb-2">{t('menu.language')}</p>
              <DesktopLanguagePicker compact />
            </div>
            <button
              type="button"
              onClick={() => { setOpen(false); dispatchOpenMissionControl(); }}
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-white/70 hover:bg-white/5 transition"
            >
              Mission Control
              <kbd className="ml-auto text-[10px] px-1 py-0.5 rounded bg-white/5 text-white/40 font-mono">F3</kbd>
            </button>
            <button
              type="button"
              onClick={toggleSidebar}
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-white/70 hover:bg-white/5 transition"
            >
              <PanelLeft className="w-4 h-4" />
              {sidebarVisible ? 'Hide sidebar' : 'Show sidebar'}
            </button>
            <button
              type="button"
              onClick={() => { setOpen(false); onOpenHelp(); }}
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-white/70 hover:bg-white/5 transition"
            >
              Keyboard shortcuts
            </button>
            <div className="tahoe-sidebar-divider" />
            <div className="flex items-center gap-2 text-white/50 text-xs px-1">
              <User className="w-3.5 h-3.5" />
              {displayUsername}
            </div>
            <button
              type="button"
              onClick={() => { setOpen(false); onLogout(); }}
              className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-red-400/90 hover:bg-red-500/10 transition"
            >
              <LogOut className="w-4 h-4" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
