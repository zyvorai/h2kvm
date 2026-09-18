// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
// Proprietary software — see LICENSE in the repository root.
// https://zyvor.dev · info@zyvor.dev

import { Link, useLocation } from 'react-router-dom';
import { getNavGroups } from '../../navigation/h2kNav';

export function ConsoleMobileNav() {
  const { pathname } = useLocation();
  const links = getNavGroups().flatMap((g) => g.items);

  return (
    <nav className="console-mobile-nav" aria-label="Console navigation">
      <div className="console-mobile-brand">
        <span className="sidebar-mark">h</span>
        <span>h2kvm</span>
      </div>
      <div className="console-mobile-pills">
        {links.map((item) => {
          const active = item.path === '/'
            ? pathname === '/'
            : pathname === item.path || pathname.startsWith(`${item.path}/`);
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`console-mobile-pill${active ? ' active' : ''}`}
            >
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
