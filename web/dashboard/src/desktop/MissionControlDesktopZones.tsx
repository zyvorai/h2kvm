// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { cloneElement, isValidElement, type ReactNode } from 'react';
import { getNavGroups } from '../navigation/h2kNav';
import type { H2kView } from '../navigation/h2kNav';

function scaleIcon(icon: ReactNode) {
  if (isValidElement<{ className?: string; strokeWidth?: number }>(icon)) {
    return cloneElement(icon, { className: 'w-8 h-8', strokeWidth: 1.75 });
  }
  return icon;
}

type Props = {
  currentView: H2kView;
  onNavigate: (view: H2kView) => void;
};

export function MissionControlDesktopZones({ currentView, onNavigate }: Props) {
  const sections = getNavGroups();

  return (
    <div className="mission-control-desktop space-y-5" data-testid="mission-control-zones">
      <div className="grid gap-5 xl:grid-cols-2">
        {sections.map((section) => (
          <div key={section.id} className="mission-control-zone-card">
            <div>
              <h3 className="text-sm font-semibold text-white/90">{section.label}</h3>
              <p className="text-xs text-white/45 mt-0.5">Jump to any destination</p>
            </div>
            <div className="mission-control-launchpad">
              {section.items.map((item) => {
                const active = currentView === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onNavigate(item.id)}
                    className={`mission-control-app-icon ${active ? 'mission-control-app-icon-active' : ''}`}
                  >
                    <span className="mission-control-app-icon-glyph">{scaleIcon(item.icon)}</span>
                    <span className="mission-control-app-icon-label">{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
