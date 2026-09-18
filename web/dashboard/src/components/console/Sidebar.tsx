// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { Link, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { getNavGroups } from '../../navigation/h2kNav';
import { useWebSocketConnected } from '../../contexts/WebSocketContext';

const STORAGE_KEY = 'h2kvm-sidebar-collapsed';

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

export function Sidebar() {
  const { pathname } = useLocation();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const connected = useWebSocketConnected();
  const groups = getNavGroups();

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [collapsed]);

  return (
    <aside className={`sidebar${collapsed ? ' is-collapsed' : ''}`} aria-label="Console navigation">
      <div className="sidebar-brand">
        <div className="sidebar-brand-row">
          <a href="https://zyvor.dev" target="_blank" rel="noreferrer" title="Zyvor">
            <span className="sidebar-mark">h</span>
          </a>
          <button
            type="button"
            className="sidebar-collapse-btn"
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? 'Expand menu' : 'Collapse menu'}
            title={collapsed ? 'Expand menu' : 'Collapse menu'}
          >
            {collapsed ? <ChevronRight /> : <ChevronLeft />}
          </button>
        </div>
        <div className="sidebar-brand-text">
          <div className="sidebar-product">h2kvm</div>
          <div className="sidebar-sub">Migration console</div>
        </div>
      </div>
      <nav className="sidebar-nav">
        {groups.map((group) => (
          <div key={group.id}>
            <div className="sidebar-group">{group.label}</div>
            {group.items.map((item) => {
              const active = item.path === '/'
                ? pathname === '/'
                : pathname === item.path || pathname.startsWith(`${item.path}/`);
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`sidebar-link${active ? ' active' : ''}`}
                  title={item.label}
                >
                  <span className="sidebar-link-icon" aria-hidden>{item.icon}</span>
                  <span className="sidebar-link-label">{item.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="sidebar-status" title={connected ? 'Live updates connected' : 'Live updates offline'}>
        <span
          className="sidebar-status-dot"
          style={{ background: connected ? 'var(--zy-ok)' : 'var(--zy-warn)' }}
        />
        <div className="sidebar-status-text">
          <span
            className="sidebar-status-label"
            style={{ color: connected ? 'var(--zy-ok)' : 'var(--zy-warn)' }}
          >
            {connected ? 'Live' : 'Offline'}
          </span>
          <div className="sidebar-uptime">{connected ? 'websocket' : 'reconnecting'}</div>
        </div>
      </div>
    </aside>
  );
}
