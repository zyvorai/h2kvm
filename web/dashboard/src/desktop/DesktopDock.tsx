// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Home, ArrowRightLeft, Monitor, ListChecks, Settings, Search, Cloud } from 'lucide-react';
import { navLabelForView } from '../navigation/h2kNav';
import type { H2kView } from '../navigation/h2kNav';
import { useDesktopTier } from '../hooks/useDesktopTier';
import { DOCK_VIEWS_BY_TIER } from '../lib/desktopTier';

const DOCK_ICONS: Record<string, typeof Home> = {
  dashboard: Home,
  migrate: ArrowRightLeft,
  vms: Monitor,
  jobmonitor: ListChecks,
  settings: Settings,
  providers: Cloud,
};

type Props = {
  currentView: H2kView;
  onNavigate: (view: H2kView) => void;
  onOpenSpotlight: () => void;
};

export function DesktopDock({ currentView, onNavigate, onOpenSpotlight }: Props) {
  const [tier] = useDesktopTier();
  const dockViews = DOCK_VIEWS_BY_TIER[tier];
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  const dock = (
    <footer className="mac-dock flex" role="navigation" aria-label="hyper2kvm dock">
      <div className="mac-dock-inner mac-dock-inner-scroll">
        {dockViews.map((view) => {
          const Icon = DOCK_ICONS[view] ?? Home;
          const active = currentView === view;
          const label = navLabelForView(view);
          return (
            <button
              key={view}
              type="button"
              title={label}
              aria-label={label}
              aria-current={active ? 'page' : undefined}
              onClick={() => onNavigate(view)}
              className={`mac-dock-item ${active ? 'mac-dock-item-active' : ''}`}
            >
              <Icon className="h-6 w-6" strokeWidth={1.75} />
              <span className="mac-dock-tooltip">{label}</span>
              {active ? <span className="mac-dock-dot" aria-hidden /> : null}
            </button>
          );
        })}
        <div className="mac-dock-divider" aria-hidden />
        <button
          type="button"
          onClick={onOpenSpotlight}
          className="mac-dock-spotlight"
          title="Spotlight (⌘K)"
          aria-label="Open Spotlight"
        >
          <Search className="h-4 w-4" />
          <span className="hidden xl:inline">Spotlight</span>
        </button>
      </div>
    </footer>
  );

  if (!mounted) return null;
  return createPortal(dock, document.body);
}
