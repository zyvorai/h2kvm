// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { useEffect, type ReactNode } from 'react';
import { useTheme, type AppTheme } from '../contexts/ThemeContext';
import { useDesktop, DesktopProvider } from './DesktopContext';
import { DesktopMobileJumpNav } from './DesktopMobileJumpNav';
import { DesktopMenubar } from './DesktopMenubar';
import { DesktopStatusIsland } from './DesktopStatusIsland';
import { DesktopControlCenter } from './DesktopControlCenter';
import { DesktopContextBar } from './DesktopContextBar';
import { DesktopSidebar } from './DesktopSidebar';
import { DesktopDock } from './DesktopDock';
import { MissionControlOverlay } from './MissionControlOverlay';
import { MissionControlProvider, useMissionControl, OPEN_MISSION_CONTROL_EVENT } from './MissionControlContext';
import type { H2kView } from '../navigation/h2kNav';
import type { NavRecent } from '../lib/navRecents';

type ShellProps = {
  currentView: H2kView;
  currentPath: string;
  navRecents: NavRecent[];
  onNavigate: (view: H2kView) => void;
  onNavigatePath: (path: string) => void;
  onOpenSpotlight: () => void;
  onOpenHelp: () => void;
  onOpenAbout: () => void;
  onLogout: () => void;
  displayUsername: string;
  wsConnected: boolean;
  serverVersion?: string;
  children: ReactNode;
};

function DesktopShell({
  currentView,
  currentPath,
  navRecents,
  onNavigate,
  onNavigatePath,
  onOpenSpotlight,
  onOpenHelp,
  onOpenAbout,
  onLogout,
  displayUsername,
  wsConnected,
  serverVersion,
  children,
}: ShellProps) {
  const { theme, wallpaper } = useTheme();
  const { sidebarVisible } = useDesktop();
  const { openMissionControl } = useMissionControl();

  useEffect(() => {
    const open = () => openMissionControl();
    window.addEventListener(OPEN_MISSION_CONTROL_EVENT, open);
    return () => window.removeEventListener(OPEN_MISSION_CONTROL_EVENT, open);
  }, [openMissionControl]);

  const shellBg: Record<AppTheme, string> = {
    dark: 'dashboard-liquid-glass',
    steel: 'dashboard-steel',
    aurora: 'dashboard-aurora',
  };

  return (
    <div
      className={`mac-desktop-root platform-mac-desktop tahoe-page-root ${shellBg[theme]} liquid-glass-app flex flex-col flex-1 min-h-0 h-full overflow-x-hidden`}
      data-wallpaper={wallpaper}
    >
      <header className="mac-menubar-inner glass shrink-0 relative z-40 flex items-center gap-2 px-2 lg:px-3 h-11 overflow-visible">
        <div className="flex items-center min-w-0 shrink-0 overflow-visible z-[400]">
          <DesktopMenubar
            currentView={currentView}
            currentPath={currentPath}
            navRecents={navRecents}
            onNavigate={onNavigate}
            onNavigatePath={onNavigatePath}
            onOpenSpotlight={onOpenSpotlight}
            onOpenHelp={onOpenHelp}
            onOpenAbout={onOpenAbout}
          />
        </div>
        <div className="flex-1 flex justify-center min-w-0 pointer-events-none">
          <DesktopStatusIsland connected={wsConnected} version={serverVersion} />
        </div>
        <div className="ml-auto shrink-0 flex items-center gap-2 z-[400]">
          <DesktopControlCenter
            displayUsername={displayUsername}
            onLogout={onLogout}
            onOpenHelp={onOpenHelp}
          />
        </div>
      </header>

      <DesktopContextBar currentView={currentView} onNavigate={onNavigate} />
      <DesktopMobileJumpNav currentView={currentView} onNavigate={onNavigate} />

      <div className="flex flex-1 min-h-0">
        {sidebarVisible ? (
          <DesktopSidebar currentView={currentView} onNavigate={onNavigate} />
        ) : null}
        <div className="tahoe-canvas mac-desktop-main flex-1 min-w-0 flex flex-col relative">
          <div className="tahoe-mesh pointer-events-none" aria-hidden />
          <div className="relative z-[1] flex flex-col flex-1 min-h-0 px-4 lg:px-6 pt-1 pb-16 lg:pb-20 max-w-[160rem] mx-auto w-full">
            <div className="flex-1 min-h-0 overflow-y-auto platform-readable tahoe-readable-stack py-3 pb-6">
              {children}
            </div>
          </div>
        </div>
      </div>

      <DesktopDock
        currentView={currentView}
        onNavigate={onNavigate}
        onOpenSpotlight={onOpenSpotlight}
      />
      <MissionControlOverlay
        currentView={currentView}
        onNavigate={onNavigate}
        wsConnected={wsConnected}
        serverVersion={serverVersion}
      />
    </div>
  );
}

export function DesktopLayout(props: ShellProps) {
  return (
    <DesktopProvider>
      <MissionControlProvider>
        <DesktopShell {...props} />
      </MissionControlProvider>
    </DesktopProvider>
  );
}
