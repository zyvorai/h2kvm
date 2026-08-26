// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Info, Keyboard, Search } from 'lucide-react';
import { getNavGroups, navLabelForView } from '../navigation/h2kNav';
import type { NavRecent } from '../lib/navRecents';
import type { H2kView } from '../navigation/h2kNav';
import { DesktopNavRecents } from './DesktopNavRecents';
import { useDesktopTier } from '../hooks/useDesktopTier';
import type { DesktopTier } from '../lib/desktopTier';
import { dispatchOpenMissionControl } from './MissionControlContext';
import { buildMenubarMenus } from './buildMenubarMenus';

type Props = {
  currentView: H2kView;
  currentPath: string;
  navRecents: NavRecent[];
  onNavigate: (view: H2kView) => void;
  onNavigatePath: (path: string) => void;
  onOpenSpotlight: () => void;
  onOpenHelp: () => void;
  onOpenAbout: () => void;
};

export function DesktopMenubar({
  currentView,
  currentPath,
  navRecents,
  onNavigate,
  onNavigatePath,
  onOpenSpotlight,
  onOpenHelp,
  onOpenAbout,
}: Props) {
  const [tier, setTier] = useDesktopTier();
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const viewLabel = navLabelForView(currentView);
  const appMenus = useMemo(() => buildMenubarMenus(getNavGroups()), []);

  useEffect(() => {
    if (!openMenu) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpenMenu(null);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [openMenu]);

  const handleAction = (action: string) => {
    setOpenMenu(null);
    if (action === 'spotlight') { onOpenSpotlight(); return; }
    if (action === 'mission') { dispatchOpenMissionControl(); return; }
    if (action === 'shortcuts') { onOpenHelp(); return; }
    if (action === 'about') { onOpenAbout(); return; }
    if (action === 'tier-normal') { setTier('normal'); return; }
    if (action === 'tier-power') { setTier('power'); return; }
    if (action === 'tier-advanced') { setTier('advanced'); return; }
    onNavigate(action as H2kView);
  };

  const isTierChecked = (action: string) => {
    const map: Record<string, DesktopTier> = {
      'tier-normal': 'normal',
      'tier-power': 'power',
      'tier-advanced': 'advanced',
    };
    return map[action] === tier;
  };

  return (
    <div ref={menuRef} className="flex items-center gap-0.5 min-w-0 shrink-0">
      {appMenus.map((menu) => (
        <div key={menu.label} className="relative">
          <button
            type="button"
            onClick={() => setOpenMenu(openMenu === menu.label ? null : menu.label)}
            className={`flex items-center gap-0.5 px-2.5 py-1 rounded-md text-xs font-medium transition ${
              openMenu === menu.label ? 'bg-white/10 text-white' : 'text-white/70 hover:bg-white/5 hover:text-white'
            }`}
          >
            {menu.label}
            {menu.label !== 'hyper2kvm' && <ChevronDown className="w-3 h-3 opacity-60" />}
          </button>
          {openMenu === menu.label && (
            <div className="absolute top-full left-0 mt-1 min-w-[11rem] max-h-[min(24rem,70vh)] overflow-y-auto rounded-xl border border-white/10 glass-strong p-1 shadow-2xl z-[500]">
              {menu.items.map((item) => (
                <button
                  key={`${menu.label}-${item.action}`}
                  type="button"
                  onClick={() => handleAction(item.action)}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-xs text-white/75 hover:bg-white/5 hover:text-white transition text-left"
                >
                  {item.action === 'spotlight' && <Search className="w-3.5 h-3.5 text-blue-400" />}
                  {item.action === 'shortcuts' && <Keyboard className="w-3.5 h-3.5" />}
                  {item.action === 'about' && <Info className="w-3.5 h-3.5" />}
                  {item.label}
                  {'shortcut' in item && item.shortcut ? (
                    <kbd className="ml-auto text-[10px] px-1 py-0.5 rounded bg-white/5 text-white/40 font-mono">{item.shortcut}</kbd>
                  ) : null}
                  {'tier' in item && item.tier && isTierChecked(item.action) ? (
                    <span className="ml-auto text-[10px] text-blue-400">✓</span>
                  ) : null}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
      <DesktopNavRecents recents={navRecents} currentPath={currentPath} onNavigatePath={onNavigatePath} />
      <span className="hidden xl:inline text-white/40 text-xs ml-1 truncate max-w-[10rem]" title={viewLabel}>
        {viewLabel}
      </span>
    </div>
  );
}
