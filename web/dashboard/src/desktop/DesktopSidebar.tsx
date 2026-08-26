// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { useCallback, useState } from 'react';
import { ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { getNavGroups } from '../navigation/h2kNav';
import type { H2kView } from '../navigation/h2kNav';
import { useDesktop } from './DesktopContext';

const SECTION_COLLAPSE_PREFIX = 'h2kweb-sidebar-section-';

function loadSectionCollapsed(label: string, defaultCollapsed: boolean): boolean {
  try {
    const raw = localStorage.getItem(`${SECTION_COLLAPSE_PREFIX}${label}`);
    if (raw === '0') return false;
    if (raw === '1') return true;
  } catch { /* ignore */ }
  return defaultCollapsed;
}

type Props = {
  currentView: H2kView;
  onNavigate: (view: H2kView) => void;
};

export function DesktopSidebar({ currentView, onNavigate }: Props) {
  const { sidebarCollapsed, setSidebarCollapsed } = useDesktop();
  const groups = getNavGroups();
  const [sectionCollapsed, setSectionCollapsed] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(
      groups.map((s) => [s.id, loadSectionCollapsed(s.id, false)])
    )
  );

  const toggleSection = useCallback((label: string) => {
    setSectionCollapsed((prev) => {
      const next = !prev[label];
      try { localStorage.setItem(`${SECTION_COLLAPSE_PREFIX}${label}`, next ? '1' : '0'); } catch { /* ignore */ }
      return { ...prev, [label]: next };
    });
  }, []);

  return (
    <aside
      className={`mac-finder-sidebar tahoe-sidebar-expanded platform-sidebar glass glass-elevated hidden lg:flex flex-col shrink-0 border-r border-white/[0.06] ${
        sidebarCollapsed ? 'w-[60px]' : 'w-[280px]'
      }`}
      aria-label="h2kvm Finder"
    >
      {!sidebarCollapsed && (
        <div className="px-5 py-4 border-b border-white/[0.06]">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-white/40">Desktop</p>
          <p className="text-sm text-white/75 mt-1">h2kvm</p>
        </div>
      )}
      <nav className="flex-1 overflow-y-auto py-3 px-3 space-y-2 min-h-0">
        {groups.map((section, sectionIdx) => {
          const isFavorites = sectionIdx === 0;
          const hasActiveItem = section.items.some((item) => item.id === currentView);
          const isClosed = section.collapsible && sectionCollapsed[section.id] && !hasActiveItem;
          return (
            <div key={section.id} className="tahoe-sidebar-section">
              {!sidebarCollapsed && !isFavorites && (
                section.collapsible ? (
                  <button
                    type="button"
                    onClick={() => toggleSection(section.id)}
                    className="tahoe-sidebar-section-header flex w-full items-center gap-1.5 px-3 py-2 mb-1 text-[10px] font-semibold uppercase tracking-wider text-white/35 hover:text-white/55 transition"
                  >
                    <ChevronDown className={`h-3 w-3 shrink-0 transition-transform ${isClosed ? '-rotate-90' : ''}`} />
                    <span className="truncate">{section.label}</span>
                  </button>
                ) : (
                  <p className="tahoe-sidebar-section-header px-3 py-2 mb-1 text-[10px] font-semibold uppercase tracking-wider text-white/35">
                    {section.label}
                  </p>
                )
              )}
              {!isClosed && (
                <ul className="space-y-1">
                  {section.items.map((item) => {
                    const active = currentView === item.id;
                    return (
                      <li key={item.id}>
                        <button
                          type="button"
                          title={sidebarCollapsed ? item.label : undefined}
                          onClick={() => onNavigate(item.id)}
                          className={`tahoe-sidebar-link flex items-center gap-3 px-3 py-2.5 text-sm transition-all duration-200 w-full ${
                            sidebarCollapsed ? 'justify-center rounded-xl' : 'rounded-full'
                          } ${
                            active
                              ? 'tahoe-sidebar-link-active text-white'
                              : 'text-white/55 hover:text-white/90 hover:bg-white/[0.04]'
                          }`}
                        >
                          <span className="shrink-0 opacity-80">{item.icon}</span>
                          {!sidebarCollapsed && <span className="truncate">{item.label}</span>}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
              {!sidebarCollapsed && sectionIdx < groups.length - 1 && (
                <div className="tahoe-sidebar-divider mx-3 my-3" aria-hidden />
              )}
            </div>
          );
        })}
      </nav>
      <div className="border-t border-white/[0.06] p-3">
        <button
          type="button"
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          className="flex w-full items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-xs text-white/50 hover:bg-white/5 hover:text-white/90 transition"
          title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {sidebarCollapsed ? <ChevronRight className="h-4 w-4" /> : (
            <>
              <ChevronLeft className="h-4 w-4" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
