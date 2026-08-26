// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { useMemo } from 'react';
import { Compass } from 'lucide-react';
import { getNavGroups } from '../navigation/h2kNav';
import type { H2kView } from '../navigation/h2kNav';

type Props = {
  currentView: H2kView;
  onNavigate: (view: H2kView) => void;
};

export function DesktopMobileJumpNav({ currentView, onNavigate }: Props) {
  const groups = useMemo(() => getNavGroups(), []);
  const groupLabel = useMemo(() => {
    for (const g of groups) {
      if (g.items.some((i) => i.id === currentView)) return g.label;
    }
    return groups[0]?.label ?? 'Home';
  }, [currentView, groups]);

  return (
    <nav
      className="tahoe-mobile-jump lg:hidden shrink-0 border-b border-white/[0.06] glass"
      aria-label="Jump navigation"
    >
      <label htmlFor="h2kweb-mobile-jump-select" className="sr-only">
        Navigate h2kvm
      </label>
      <div className="flex items-center gap-2 px-4 py-2.5">
        <Compass className="h-4 w-4 shrink-0 text-sky-400/80" aria-hidden />
        <select
          id="h2kweb-mobile-jump-select"
          className="tahoe-mobile-jump-select flex-1 min-w-0"
          value={currentView}
          onChange={(e) => onNavigate(e.target.value as H2kView)}
        >
          {groups.map((section) => (
            <optgroup key={section.id} label={section.label}>
              {section.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        <span className="text-[10px] text-white/35 shrink-0">{groupLabel}</span>
      </div>
    </nav>
  );
}
