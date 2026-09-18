// Copyright (c) 2026 ZyvorAI Labs Private Limited.
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
// https://zyvor.dev · info@zyvor.dev

import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { ConsoleMobileNav } from './ConsoleMobileNav';
import { ConsoleTopbar } from './ConsoleTopbar';
import { useTheme } from '../../contexts/ThemeContext';
import { useAuthStore } from '../../stores/auth';

type Props = {
  children: ReactNode;
  realm?: string;
  onOpenPalette?: () => void;
};

export function ConsoleLayout({ children, realm, onOpenPalette }: Props) {
  const { toggle, resolved } = useTheme();
  const { username, logout } = useAuthStore();
  const navigate = useNavigate();
  const initials = (username || 'h2').slice(0, 2).toUpperCase();

  return (
    <div className="console-layout">
      <ConsoleMobileNav />
      <Sidebar />
      <div className="console-main">
        <ConsoleTopbar
          realm={realm}
          onOpenPalette={onOpenPalette}
          trailing={
            <div className="console-user">
              <span className="console-user-chip" title={username || 'admin'}>{initials}</span>
              <button
                type="button"
                className="console-signout"
                onClick={async () => {
                  await logout();
                  navigate('/');
                  window.location.reload();
                }}
              >
                Sign out
              </button>
              <button
                type="button"
                className="theme-toggle-btn"
                onClick={toggle}
                aria-label={resolved === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
                title={resolved === 'dark' ? 'Light mode' : 'Dark mode'}
              >
                {resolved === 'dark' ? '☀' : '☾'}
              </button>
            </div>
          }
        />
        <div className="console-content">{children}</div>
      </div>
    </div>
  );
}
