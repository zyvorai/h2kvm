// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { getNavGroups, navGroupForView } from '../navigation/h2kNav';
import type { H2kView } from '../navigation/h2kNav';
import { Home, ArrowRightLeft, Server, Settings } from 'lucide-react';
import { splitContextNavItems } from './desktopContextNav';

const GROUP_ICONS: Record<string, typeof Home> = {
  home: Home,
  migrate: ArrowRightLeft,
  infrastructure: Server,
  system: Settings,
};

type Props = {
  currentView: H2kView;
  onNavigate: (view: H2kView) => void;
};

export function DesktopContextBar({ currentView, onNavigate }: Props) {
  const [moreOpen, setMoreOpen] = useState(false);
  const groupId = navGroupForView(currentView);

  const ctx = useMemo(() => {
    if (!groupId) return null;
    const group = getNavGroups().find((g) => g.id === groupId);
    if (!group || group.items.length <= 1) return null;
    return { label: group.label, items: group.items };
  }, [groupId]);

  const { visible, overflow } = useMemo(() => {
    if (!ctx) return { visible: [], overflow: [] };
    return splitContextNavItems(ctx.items, currentView);
  }, [ctx, currentView]);

  useEffect(() => {
    if (!moreOpen) return;
    const close = () => setMoreOpen(false);
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    window.addEventListener('click', close);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('click', close);
      window.removeEventListener('keydown', onKey);
    };
  }, [moreOpen]);

  if (!ctx) return null;

  const GroupIcon = GROUP_ICONS[groupId ?? ''] ?? Home;

  return (
    <div className="tahoe-context-bar shrink-0 relative z-30">
      <div className="tahoe-context-bar-inner flex items-center gap-3 min-w-0">
        <div className="flex items-center gap-2 shrink-0">
          <div className="tahoe-context-app-icon">
            <GroupIcon className="w-3.5 h-3.5" />
          </div>
          <button
            type="button"
            onClick={() => onNavigate(ctx.items[0].id)}
            className="tahoe-context-app-title"
          >
            {ctx.label}
          </button>
        </div>
        <div className="tahoe-context-pills flex items-center gap-1.5 flex-1 min-w-0">
          {visible.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onNavigate(item.id)}
              className={`tahoe-context-pill ${currentView === item.id ? 'tahoe-context-pill-active' : ''}`}
              aria-current={currentView === item.id ? 'page' : undefined}
            >
              {item.label}
            </button>
          ))}
          {overflow.length > 0 && (
            <div className="relative shrink-0">
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setMoreOpen((v) => !v); }}
                className={`tahoe-context-pill tahoe-context-more flex items-center gap-1 ${moreOpen ? 'tahoe-context-pill-active' : ''}`}
                aria-expanded={moreOpen}
                aria-haspopup="menu"
              >
                More
                <ChevronDown className={`w-3 h-3 transition-transform ${moreOpen ? 'rotate-180' : ''}`} />
              </button>
              {moreOpen && (
                <div
                  className="tahoe-context-overflow-menu"
                  role="menu"
                  onClick={(e) => e.stopPropagation()}
                >
                  {overflow.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      role="menuitem"
                      onClick={() => { onNavigate(item.id); setMoreOpen(false); }}
                      className={`tahoe-context-overflow-item w-full text-left ${
                        currentView === item.id ? 'tahoe-context-overflow-item-active' : ''
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
