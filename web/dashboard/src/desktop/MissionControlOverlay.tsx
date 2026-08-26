// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { X, Activity, Server, ListChecks } from 'lucide-react';
import { navLabelForView } from '../navigation/h2kNav';
import type { H2kView } from '../navigation/h2kNav';
import { useKeyboardShortcut } from '../hooks/useKeyboardShortcut';
import { useDesktopTier } from '../hooks/useDesktopTier';
import { DESKTOP_TIER_LABELS } from '../lib/desktopTier';
import { MissionControlDesktopZones } from './MissionControlDesktopZones';
import { useMissionControl } from './MissionControlContext';

type Props = {
  currentView: H2kView;
  onNavigate: (view: H2kView) => void;
  wsConnected: boolean;
  serverVersion?: string;
};

export function MissionControlOverlay({ currentView, onNavigate, wsConnected, serverVersion }: Props) {
  const { open, closeMissionControl } = useMissionControl();
  const [tier] = useDesktopTier();

  useKeyboardShortcut({
    key: 'Escape',
    handler: () => { if (open) closeMissionControl(); },
    enabled: open,
  });

  if (!open) return null;

  const handleNavigate = (view: H2kView) => {
    onNavigate(view);
    closeMissionControl();
  };

  return (
    <div
      className="mission-control-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Mission Control"
      data-testid="mission-control-overlay"
    >
      <button
        type="button"
        className="mission-control-backdrop"
        aria-label="Close Mission Control"
        onClick={closeMissionControl}
      />
      <div className="mission-control-panel">
        <header className="mission-control-header">
          <div>
            <h1 className="text-xl font-bold text-white/95">Mission Control</h1>
            <p className="text-sm text-white/45 mt-0.5">
              h2kvm desktop · {DESKTOP_TIER_LABELS[tier]} · {navLabelForView(currentView)}
            </p>
          </div>
          <button
            type="button"
            className="tahoe-btn-ghost flex items-center gap-2"
            onClick={closeMissionControl}
          >
            <X className="w-4 h-4" />
            Close
          </button>
        </header>

        <div className="mission-control-stats">
          <div className={`mission-control-stat ${wsConnected ? 'mission-control-stat-ok' : 'mission-control-stat-warn'}`}>
            <Activity className="w-4 h-4" />
            <span>{wsConnected ? 'Daemon connected' : 'Daemon offline'}</span>
          </div>
          {serverVersion ? (
            <div className="mission-control-stat">
              <Server className="w-4 h-4" />
              <span>v{serverVersion}</span>
            </div>
          ) : null}
          <div className="mission-control-stat">
            <ListChecks className="w-4 h-4" />
            <span>Current: {navLabelForView(currentView)}</span>
          </div>
        </div>

        <MissionControlDesktopZones currentView={currentView} onNavigate={handleNavigate} />
      </div>
    </div>
  );
}
