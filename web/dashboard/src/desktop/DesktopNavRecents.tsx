// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import type { NavRecent } from '../lib/navRecents';

type Props = {
  recents: NavRecent[];
  currentPath: string;
  onNavigatePath: (path: string) => void;
};

export function DesktopNavRecents({ recents, currentPath, onNavigatePath }: Props) {
  const filtered = recents.filter((r) => r.id !== currentPath && r.id !== '/').slice(0, 3);
  if (filtered.length === 0) return null;

  return (
    <div className="hidden lg:flex items-center gap-1 ml-2 pl-2 border-l border-white/[0.08] shrink-0">
      <span className="text-[10px] text-white/35 uppercase tracking-wider mr-0.5">Recent</span>
      {filtered.map((r) => (
        <button
          key={r.id}
          type="button"
          onClick={() => onNavigatePath(r.id)}
          className="tahoe-context-pill max-w-[7rem] truncate"
          title={r.label}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}
